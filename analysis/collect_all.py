#!/usr/bin/env python3
"""
Batch-pull CloudWatch data for every experiment in data/raw/.

Walks every *_window.json, works out which Lambda function it belongs to from
the "variant" field, and calls the same logic as pull_cloudwatch.py for each.
Skips windows whose _cloudwatch.csv already exists, so it is safe to re-run
after collecting more data.

RUNS ON YOUR LAPTOP (needs AWS credentials).

Usage:
    python3 analysis/collect_all.py
    python3 analysis/collect_all.py --force        # re-pull everything
    python3 analysis/collect_all.py --pattern burst_onnx

Function names are resolved automatically from the CloudFormation stack.
"""
import argparse
import glob
import json
import os
import subprocess
import sys

import boto3

STACK_NAME = "minilm-lambda-eval"
REGION = "us-east-1"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RAW_DIR = os.path.join(REPO_ROOT, "data", "raw")
PULLER = os.path.join(HERE, "pull_cloudwatch.py")


def resolve_function_names():
    """Map variant -> physical Lambda function name via CloudFormation."""
    cfn = boto3.client("cloudformation", region_name=REGION)
    resources = cfn.describe_stack_resources(StackName=STACK_NAME)["StackResources"]
    mapping = {}
    for r in resources:
        if r["ResourceType"] != "AWS::Lambda::Function":
            continue
        logical = r["LogicalResourceId"]
        if logical == "OnnxFunction":
            mapping["onnx"] = r["PhysicalResourceId"]
        elif logical == "PytorchFunction":
            mapping["pytorch"] = r["PhysicalResourceId"]
    missing = {"onnx", "pytorch"} - set(mapping)
    if missing:
        sys.exit(f"Could not resolve function(s) {missing} from stack {STACK_NAME}")
    return mapping


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--force", action="store_true", help="Re-pull even if CSV exists")
    p.add_argument("--pattern", default="", help="Only windows whose name contains this")
    args = p.parse_args()

    if not os.path.isdir(RAW_DIR):
        sys.exit(f"No such directory: {RAW_DIR}\nPull the CSVs from EC2 first.")

    functions = resolve_function_names()
    print(f"Resolved functions:\n  onnx    -> {functions['onnx']}\n"
          f"  pytorch -> {functions['pytorch']}\n")

    windows = sorted(glob.glob(os.path.join(RAW_DIR, "*_window.json")))
    if args.pattern:
        windows = [w for w in windows if args.pattern in os.path.basename(w)]

    if not windows:
        sys.exit("No *_window.json files found.")

    done = skipped = failed = 0
    for wpath in windows:
        csv_path = wpath.replace("_window.json", "_cloudwatch.csv")
        if os.path.exists(csv_path) and not args.force:
            skipped += 1
            continue

        with open(wpath) as f:
            w = json.load(f)
        variant = w.get("variant", "onnx")
        fn = functions.get(variant)
        if not fn:
            print(f"  SKIP {os.path.basename(wpath)}: unknown variant {variant!r}")
            failed += 1
            continue

        cmd = [sys.executable, PULLER, "--window", wpath,
               "--function", fn, "--region", REGION, "--quiet"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  FAIL {os.path.basename(wpath)}")
            print("       " + result.stderr.strip().replace("\n", "\n       "))
            failed += 1
        else:
            print(f"  OK   {result.stdout.strip()}")
            done += 1

    print(f"\nPulled {done}, skipped {skipped} (already present), failed {failed}.")
    if skipped and not args.force:
        print("Use --force to re-pull the skipped ones.")


if __name__ == "__main__":
    main()
