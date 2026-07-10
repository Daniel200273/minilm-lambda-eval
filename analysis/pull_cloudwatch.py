#!/usr/bin/env python3
"""
Pull CloudWatch data for one Lambda function over one experiment's time window.

RUNS ON YOUR LAPTOP (needs valid AWS credentials => Learner Lab session must be
started). NOT on the EC2 load generator.

Two ways to give the window:

  1. From a _window.json written by load_testing/run_experiment.sh:
       python3 analysis/pull_cloudwatch.py \\
           --window data/raw/burst_onnx_n10_run1_window.json \\
           --function minilm-lambda-eval-OnnxFunction-XXXX

  2. Explicit ISO8601 UTC timestamps:
       python3 analysis/pull_cloudwatch.py --function <fn> \\
           --start 2026-07-09T10:00:00Z --end 2026-07-09T10:05:00Z

Find the physical function names with:
  aws cloudformation describe-stack-resources --stack-name minilm-lambda-eval \\
      --region us-east-1 \\
      --query "StackResources[?ResourceType=='AWS::Lambda::Function'].[LogicalResourceId,PhysicalResourceId]" \\
      --output table

Outputs a CSV with one row per Lambda invocation (parsed from REPORT log lines)
and prints aggregate CloudWatch metrics for the same window.

A margin is added to the query window because CloudWatch log ingestion lags a
few seconds behind the invocation; without it the last invocations of a run can
be missed.
"""
import argparse
import csv
import json
import re
import sys
from datetime import datetime, timedelta, timezone

import boto3

# Lambda REPORT lines. Init Duration is present only on cold starts.
REPORT_RE = re.compile(
    r"Duration:\s*(?P<duration>[\d.]+)\s*ms\s+"
    r"Billed Duration:\s*(?P<billed>[\d.]+)\s*ms\s+"
    r"Memory Size:\s*(?P<mem_size>\d+)\s*MB\s+"
    r"Max Memory Used:\s*(?P<mem_used>\d+)\s*MB"
    r"(?:\s+Init Duration:\s*(?P<init>[\d.]+)\s*ms)?"
)

MARGIN = timedelta(seconds=30)


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--function", required=True, help="Lambda physical function name")
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--window", help="Path to a _window.json from run_experiment.sh")
    p.add_argument("--start", help="ISO8601 UTC, e.g. 2026-07-09T10:00:00Z")
    p.add_argument("--end", help="ISO8601 UTC")
    p.add_argument("--out", help="Output CSV path")
    p.add_argument("--quiet", action="store_true", help="Suppress the metrics summary")
    return p.parse_args()


def parse_iso(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def fetch_report_lines(logs, function, start_dt, end_dt):
    log_group = f"/aws/lambda/{function}"
    rows = []
    kwargs = {
        "logGroupName": log_group,
        "startTime": int(start_dt.timestamp() * 1000),
        "endTime": int(end_dt.timestamp() * 1000),
        "filterPattern": "REPORT",
    }
    while True:
        try:
            resp = logs.filter_log_events(**kwargs)
        except logs.exceptions.ResourceNotFoundException:
            sys.exit(
                f"Log group not found: {log_group}\n"
                "Check --function is the exact PHYSICAL function name."
            )
        for ev in resp.get("events", []):
            m = REPORT_RE.search(ev["message"])
            if not m:
                continue
            rows.append(
                {
                    "timestamp_ms": ev["timestamp"],
                    "timestamp_utc": datetime.fromtimestamp(
                        ev["timestamp"] / 1000, tz=timezone.utc
                    ).isoformat(),
                    "duration_ms": float(m.group("duration")),
                    "billed_duration_ms": float(m.group("billed")),
                    "memory_size_mb": int(m.group("mem_size")),
                    "max_memory_used_mb": int(m.group("mem_used")),
                    "init_duration_ms": float(m.group("init")) if m.group("init") else "",
                    "cold_start": 1 if m.group("init") else 0,
                }
            )
        token = resp.get("nextToken")
        if not token:
            break
        kwargs["nextToken"] = token
    rows.sort(key=lambda r: r["timestamp_ms"])
    return rows


def fetch_aggregates(cw, function, start_dt, end_dt):
    period = max(60, int((end_dt - start_dt).total_seconds()))
    out = {}
    for metric, stat in [
        ("Invocations", "Sum"),
        ("Throttles", "Sum"),
        ("Errors", "Sum"),
        ("ConcurrentExecutions", "Maximum"),
    ]:
        resp = cw.get_metric_statistics(
            Namespace="AWS/Lambda",
            MetricName=metric,
            Dimensions=[{"Name": "FunctionName", "Value": function}],
            StartTime=start_dt,
            EndTime=end_dt,
            Period=period,
            Statistics=[stat],
        )
        dps = resp.get("Datapoints", [])
        if not dps:
            out[metric] = 0
        elif stat == "Sum":
            out[metric] = sum(d["Sum"] for d in dps)
        else:
            out[metric] = max(d["Maximum"] for d in dps)
    return out


def main():
    args = parse_args()

    if args.window:
        with open(args.window) as f:
            w = json.load(f)
        start_dt, end_dt = parse_iso(w["start"]), parse_iso(w["end"])
        out_path = args.out or args.window.replace("_window.json", "_cloudwatch.csv")
    elif args.start and args.end:
        start_dt, end_dt = parse_iso(args.start), parse_iso(args.end)
        out_path = args.out or "cloudwatch_pull.csv"
    else:
        sys.exit("Give either --window, or both --start and --end.")

    q_start, q_end = start_dt - MARGIN, end_dt + MARGIN

    logs = boto3.client("logs", region_name=args.region)
    cw = boto3.client("cloudwatch", region_name=args.region)

    rows = fetch_report_lines(logs, args.function, q_start, q_end)

    if rows:
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    if args.quiet:
        print(f"{out_path}: {len(rows)} invocations")
        return

    print(f"Function : {args.function}")
    print(f"Window   : {start_dt.isoformat()} -> {end_dt.isoformat()}")
    print(f"Invocations parsed from REPORT lines: {len(rows)}")

    if not rows:
        print("\nNo REPORT lines found. Either the window is wrong, the function name is "
              "wrong, or CloudWatch has not ingested the logs yet (wait ~30 s and retry).")
        return

    print(f"Saved -> {out_path}")

    durations = [r["duration_ms"] for r in rows]
    cold = [r for r in rows if r["cold_start"]]
    print("\nPer-invocation summary (from REPORT lines):")
    print(f"  MinT / AvgT / MaxT : {min(durations):.2f} / "
          f"{sum(durations)/len(durations):.2f} / {max(durations):.2f} ms")
    print(f"  MaxMemoryUsed      : {max(r['max_memory_used_mb'] for r in rows)} MiB "
          f"(of {rows[0]['memory_size_mb']} MiB allocated)")
    print(f"  Cold starts        : {len(cold)}")
    if cold:
        inits = [r["init_duration_ms"] for r in cold]
        print(f"  InitDuration avg   : {sum(inits)/len(inits):.2f} ms")

    agg = fetch_aggregates(cw, args.function, q_start, q_end)
    print("\nAggregate CloudWatch metrics:")
    for k, v in agg.items():
        print(f"  {k:22s}: {v}")


if __name__ == "__main__":
    main()
