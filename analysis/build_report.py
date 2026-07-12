#!/usr/bin/env python3
"""
Turns everything in data/raw/ into the report's exact tables (CSV + Markdown)
and figures (PNG) - shapes, column names, and variant scope all matched
directly against the report text.

Run on the laptop, after all tests have run and collect_all.py has pulled
matching CloudWatch data.

Usage:
    python3 analysis/build_report.py

Output:
    analysis/output/tables/table3_cold_start.csv          Request# | ONNX | PyTorch (+Average row)
    analysis/output/tables/table4_burst.csv                Var,N,MinT,MaxT,AvgT,N.Conc,N.Invc,CliT,MaxMem,N.Fail,Fail%
    analysis/output/tables/table5_steady_<variant>.csv     Peak,Step,Time(s),Sent,Failed,Fail%
    analysis/output/tables/table6_burst_vs_steady.csv      Run 1-5 + Avg. x 6 named configs
    analysis/output/tables/table7_input_size_<variant>.csv Bucket,N,AvgT,MaxT,MaxMem,Fail%
    analysis/output/tables/table9_cost_analysis.csv        Traffic x AWS/Azure/GCP/EC2
    analysis/output/figures/figure4_framework.png          ONNX vs PyTorch, both variants
    analysis/output/figures/figure5_billed_duration_vs_memory.png   ONNX ONLY (matches caption)
    analysis/output/figures/figure6_latency_vs_memory.png  both variants, p50 AND p99
    analysis/output/figures/figure7_tail_latency.png       from STEADY runs (matches report text)
    analysis/output/figures/figure8_ramp_<variant>.png
    analysis/output/figures/figure9_topk.png               ONNX only

Every function skips gracefully (printing why) if its source files aren't
present yet - safe to run partway through data collection, safe to re-run.
"""
import warnings
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

warnings.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW = REPO_ROOT / "data" / "raw"
OUT = Path(__file__).resolve().parent / "output"
TABLES = OUT / "tables"
FIGURES = OUT / "figures"
TABLES.mkdir(parents=True, exist_ok=True)
FIGURES.mkdir(parents=True, exist_ok=True)

VARIANTS = ["onnx", "pytorch"]


# ---------------------------------------------------------------- helpers --

def save(df, name, index=False):
    df.to_csv(TABLES / f"{name}.csv", index=index)
    try:
        (TABLES / f"{name}.md").write_text(df.to_markdown(index=index))
    except ImportError:
        pass
    print(f"  wrote {name}.csv ({len(df)} rows)")


def load_stats(prefix):
    path = RAW / f"{prefix}_stats.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    agg = df[df["Name"].astype(str).str.strip() == "Aggregated"]
    return agg.iloc[0].to_dict() if not agg.empty else None


def load_cloudwatch(prefix):
    path = RAW / f"{prefix}_cloudwatch.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    return df if len(df) else None


def load_window(prefix):
    path = RAW / f"{prefix}_window.json"
    if not path.exists():
        return None
    import json
    return json.loads(path.read_text())


def window_duration_s(prefix):
    """Wall-clock duration of the test campaign, per report Sec 5.3's own
    definition of 'client-side total execution time' - NOT per-request average."""
    w = load_window(prefix)
    if w is None:
        return None
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    try:
        s = datetime.strptime(w["start"], fmt).replace(tzinfo=timezone.utc)
        e = datetime.strptime(w["end"], fmt).replace(tzinfo=timezone.utc)
        return (e - s).total_seconds()
    except Exception:
        return None


def max_concurrent(cw):
    """N. Conc. Execs via sweep-line over invocation intervals, computed
    directly from already-collected data - no new AWS calls needed.
    timestamp_ms is CloudWatch's log-ingestion time (~= invocation end);
    start is approximated as end - duration_ms."""
    if cw is None or cw.empty:
        return None
    events = []
    for _, r in cw.iterrows():
        end = r["timestamp_ms"]
        start = end - r["duration_ms"]
        events.append((start, 1))
        events.append((end, -1))
    events.sort(key=lambda x: (x[0], x[1]))  # process starts before ends at same instant... actually ends before starts is safer
    cur = peak = 0
    for _, delta in events:
        cur += delta
        peak = max(peak, cur)
    return peak


def cw_summary(cw):
    if cw is None or cw.empty:
        return dict(min_t=None, avg_t=None, max_t=None, max_mem=None, n_invc=0, n_conc=None)
    return dict(
        min_t=cw["duration_ms"].min(), avg_t=cw["duration_ms"].mean(),
        max_t=cw["duration_ms"].max(), max_mem=cw["max_memory_used_mb"].max(),
        n_invc=len(cw), n_conc=max_concurrent(cw),
    )


def find_prefixes(pattern):
    hits = sorted(RAW.glob(f"{pattern}_stats.csv"))
    return [h.name[: -len("_stats.csv")] for h in hits]


# --------------------------------------------------------- Table 3: cold ---

def table3_cold_start():
    """Report shape: Request # (1-10) as rows, ONNX(ms)/PyTorch(ms) as columns,
    Average row at the bottom. One file per variant - most recent used."""
    print("\nTable 3 - Cold start")
    per_variant = {}
    for variant in VARIANTS:
        files = sorted(RAW.glob(f"cold_start_{variant}_*.csv"))
        files = [f for f in files if "_window" not in f.stem and "_cloudwatch" not in f.stem]
        if not files:
            print(f"  skip {variant}: no cold_start_{variant}_* files found")
            continue
        prefix = files[-1].stem  # most recent
        cw = load_cloudwatch(prefix)
        if cw is None:
            print(f"  skip {variant}: {prefix} has no matching _cloudwatch.csv yet")
            continue
        cold = cw[cw["cold_start"] == 1].reset_index(drop=True)
        if len(cold) < len(cw):
            print(f"  note {variant}: {len(cw)-len(cold)} row(s) NOT confirmed cold by "
                  f"CloudWatch despite forced invalidation - excluded")
        per_variant[variant] = cold["init_duration_ms"].reset_index(drop=True)

    if not per_variant:
        print("  NO DATA")
        return

    n = max(len(v) for v in per_variant.values())
    out = pd.DataFrame({"Request #": range(1, n + 1)})
    for variant in VARIANTS:
        col = "ONNX (ms)" if variant == "onnx" else "PyTorch (ms)"
        vals = per_variant.get(variant, pd.Series(dtype=float))
        out[col] = [vals[i] if i < len(vals) else None for i in range(n)]

    avg_row = {"Request #": "Average"}
    for c in out.columns[1:]:
        avg_row[c] = round(out[c].mean(skipna=True), 2) if out[c].notna().any() else None
    out = pd.concat([out, pd.DataFrame([avg_row])], ignore_index=True)
    save(out, "table3_cold_start")


# -------------------------------------------------------- Table 4: burst ---

def table4_burst():
    """Report column order: Var,N,MinT,MaxT,AvgT,N.Conc.,N.Invc.,CliT,MaxMem,N.Fail,Fail%"""
    print("\nTable 4 - Burst traffic")
    ns = [1, 5, 10, 15, 25, 50]
    rows = []
    for variant in VARIANTS:
        for n in ns:
            per_run = []
            for prefix in find_prefixes(f"burst_{variant}_n{n}_run*"):
                stats = load_stats(prefix)
                if stats is None:
                    continue
                cw = load_cloudwatch(prefix)
                cws = cw_summary(cw)
                per_run.append({
                    "req_count": stats.get("Request Count", 0),
                    "fail_count": stats.get("Failure Count", 0),
                    "min_t": cws["min_t"], "avg_t": cws["avg_t"], "max_t": cws["max_t"],
                    "n_conc": cws["n_conc"], "n_invc": cws["n_invc"], "max_mem": cws["max_mem"],
                    "cli_t": window_duration_s(prefix),
                })
            if not per_run:
                continue
            pr = pd.DataFrame(per_run)
            total_req = pr["req_count"].sum()
            total_fail = pr["fail_count"].sum()
            rows.append({
                "Var": variant.upper() if variant == "onnx" else "PT",
                "N": n,
                "MinT_ms": round(pr["min_t"].mean(), 2),
                "MaxT_ms": round(pr["max_t"].mean(), 2),
                "AvgT_ms": round(pr["avg_t"].mean(), 2),
                "N_Conc_Execs": round(pr["n_conc"].mean(), 1) if pr["n_conc"].notna().any() else None,
                "N_Invc": round(pr["n_invc"].mean(), 1),
                "CliT_s": round(pr["cli_t"].mean(), 2) if pr["cli_t"].notna().any() else None,
                "MaxMem_MB": round(pr["max_mem"].mean(), 1),
                "N_Fail": round(total_fail / len(pr), 1),
                "FailRate_pct": round(100 * total_fail / total_req, 2) if total_req else 0,
                "n_runs": len(pr),
            })
    if not rows:
        print("  NO DATA (expected: burst_<variant>_n<N>_run<rep>_*)")
        return
    save(pd.DataFrame(rows), "table4_burst")


# ------------------------------------------------------- Table 5: steady ---

def table5_steady(variant="onnx"):
    """Report columns: Peak,Step,Time(s),Sent,Failed,Fail%"""
    print(f"\nTable 5 - Steady traffic ({variant})")
    configs = [(25, 5), (50, 10), (50, 5)]
    rows = []
    for peak, step in configs:
        per_run = []
        for prefix in find_prefixes(f"steady_{variant}_p{peak}_s{step}_run*"):
            stats = load_stats(prefix)
            if stats is None:
                continue
            per_run.append({
                "req_count": stats["Request Count"], "fail_count": stats["Failure Count"],
                "time_s": window_duration_s(prefix),
            })
        if not per_run:
            continue
        pr = pd.DataFrame(per_run)
        total_req = pr["req_count"].sum()
        total_fail = pr["fail_count"].sum()
        rows.append({
            "Peak_req_s": peak, "Step": step,
            "Time_s": round(pr["time_s"].mean(), 2) if pr["time_s"].notna().any() else None,
            "Sent": round(pr["req_count"].mean(), 1),
            "Failed": round(pr["fail_count"].mean(), 1),
            "FailRate_pct": round(100 * total_fail / total_req, 2) if total_req else 0,
            "n_runs": len(pr),
        })
    if not rows:
        print(f"  NO DATA for variant={variant}")
        return
    save(pd.DataFrame(rows), f"table5_steady_{variant}")


# ---------------------------------------------- Table 6: burst vs steady ---

def table6_burst_vs_steady():
    """Report shape: Run (1-5, +Avg.) as rows, six NAMED configs as columns:
    Steady-25, Steady-50-s10, Steady-50-s5, Burst-15, Burst-25, Burst-50
    (ONNX variant, per-run failure rate - not averaged across runs)."""
    print("\nTable 6 - Burst vs steady comparison (ONNX)")
    configs = {
        "Steady-25": "steady_onnx_p25_s5_run{}",
        "Steady-50-s10": "steady_onnx_p50_s10_run{}",
        "Steady-50-s5": "steady_onnx_p50_s5_run{}",
        "Burst-15": "burst_onnx_n15_run{}",
        "Burst-25": "burst_onnx_n25_run{}",
        "Burst-50": "burst_onnx_n50_run{}",
    }
    rows = []
    for run in range(1, 6):
        row = {"Run": run}
        for label, pattern in configs.items():
            stats = load_stats(pattern.format(run))
            if stats is None:
                row[label] = None
                continue
            total, fail = stats.get("Request Count", 0), stats.get("Failure Count", 0)
            row[label] = round(100 * fail / total, 2) if total else None
        rows.append(row)

    if all(all(v is None for k, v in r.items() if k != "Run") for r in rows):
        print("  NO DATA (expected: steady_onnx_p*/burst_onnx_n{15,25,50}_run1..5)")
        return

    df = pd.DataFrame(rows)
    avg_row = {"Run": "Avg."}
    for label in configs:
        avg_row[label] = round(df[label].mean(skipna=True), 2) if df[label].notna().any() else None
    df = pd.concat([df, pd.DataFrame([avg_row])], ignore_index=True)
    save(df, "table6_burst_vs_steady")


# ---------------------------------------------------- Table 7: input size --

def table7_input_size(variant="onnx"):
    print(f"\nTable 7 - Input size effect ({variant})")
    buckets, ns = ["short", "medium", "long"], [1, 10, 15]
    rows = []
    for bucket in buckets:
        for n in ns:
            per_run = []
            for prefix in find_prefixes(f"inputsize_{variant}_{bucket}_n{n}_run*"):
                stats = load_stats(prefix)
                if stats is None:
                    continue
                cws = cw_summary(load_cloudwatch(prefix))
                per_run.append({
                    "req_count": stats.get("Request Count", 0), "fail_count": stats.get("Failure Count", 0),
                    "avg_t": cws["avg_t"], "max_t": cws["max_t"], "max_mem": cws["max_mem"],
                })
            if not per_run:
                continue
            pr = pd.DataFrame(per_run)
            total_req, total_fail = pr["req_count"].sum(), pr["fail_count"].sum()
            rows.append({
                "Bucket": bucket.capitalize(), "N": n,
                "AvgT_ms": round(pr["avg_t"].mean(), 2), "MaxT_ms": round(pr["max_t"].mean(), 2),
                "MaxMem_MB": round(pr["max_mem"].mean(), 1),
                "FailRate_pct": round(100 * total_fail / total_req, 2) if total_req else 0,
            })
    if not rows:
        print(f"  NO DATA for variant={variant}")
        return
    save(pd.DataFrame(rows), f"table7_input_size_{variant}")


# ------------------------------------------------- Figure 4: framework -----

def figure4_framework():
    print("\nFigure 4 - Framework comparison (both variants)")
    rows = []
    for variant in VARIANTS:
        per_run = [cw_summary(load_cloudwatch(p)) for p in find_prefixes(f"framework_{variant}_50users_run*")]
        per_run = [r for r in per_run if r["avg_t"] is not None]
        if not per_run:
            continue
        rows.append({"variant": variant, "AvgT_ms": pd.DataFrame(per_run)["avg_t"].mean(), "n_runs": len(per_run)})
    if not rows:
        print("  NO DATA (expected: framework_<variant>_50users_run<rep>_*)")
        return
    df = pd.DataFrame(rows)
    save(df, "figure4_framework")

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(df["variant"], df["AvgT_ms"], color=["#4C72B0", "#DD8452"])
    ax.set_ylabel("Average execution duration (ms)")
    ax.set_title("Framework comparison - 50 concurrent users, 3008 MiB")
    for i, v in enumerate(df["AvgT_ms"]):
        ax.text(i, v, f"{v:.1f} ms", ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(FIGURES / "figure4_framework.png", dpi=150)
    plt.close(fig)
    print("  wrote figure4_framework.png")


# ------------------------------------------- Figures 5 & 6: vert scaling ---

def figures56_vertical_scaling():
    """Fig 5 caption explicitly says ONNX variant only.
    Fig 6 needs BOTH variants + BOTH p50 and p99, to support the report's
    text comparing PyTorch's greater memory sensitivity."""
    print("\nFigures 5 & 6 - Vertical scaling")
    tiers = [1024, 2048, 3008]
    rows = []
    for variant in VARIANTS:
        for mem in tiers:
            per_run = []
            for prefix in find_prefixes(f"vscale_{variant}_mem{mem}_run*"):
                stats = load_stats(prefix)
                cw = load_cloudwatch(prefix)
                if stats is None:
                    continue
                cws = cw_summary(cw)
                per_run.append({"billed_ms": cws["avg_t"], "p50": stats.get("50%"), "p99": stats.get("99%")})
            if not per_run:
                continue
            pr = pd.DataFrame(per_run)
            rows.append({"variant": variant, "memory_mb": mem,
                          "avg_billed_ms": pr["billed_ms"].mean(),
                          "p50_ms": pr["p50"].mean(), "p99_ms": pr["p99"].mean(), "n_runs": len(pr)})
    if not rows:
        print("  NO DATA (expected: vscale_<variant>_mem<tier>_run<rep>_*)")
        return
    df = pd.DataFrame(rows)
    save(df, "figure56_vertical_scaling")

    # Figure 5: ONNX ONLY (matches explicit caption)
    onnx_df = df[df["variant"] == "onnx"].sort_values("memory_mb")
    if len(onnx_df):
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(onnx_df["memory_mb"].astype(str), onnx_df["avg_billed_ms"], color="#4C72B0")
        ax.set_xlabel("Lambda memory (MiB)")
        ax.set_ylabel("Average billed duration (ms)")
        ax.set_title("Billed execution duration by memory allocation (ONNX)")
        fig.tight_layout()
        fig.savefig(FIGURES / "figure5_billed_duration_vs_memory.png", dpi=150)
        plt.close(fig)
    else:
        print("  skip figure5: no ONNX vscale data")

    # Figure 6: BOTH variants, p50 AND p99. Log scale + value labels, because
    # PyTorch's p99 runs 10-100x larger than ONNX's - on a linear axis the
    # ONNX bars flatten to invisible slivers. Log scale keeps everything
    # readable at a glance; labels give exact numbers despite the compressed
    # log spacing making bar heights harder to compare by eye alone.
    fig, ax = plt.subplots(figsize=(9, 5))
    width = 60
    offsets = {"onnx": -1.5, "pytorch": 0.5}
    colors = {"onnx": ("#4C72B0", "#A6C8FF"), "pytorch": ("#DD8452", "#FFC8A6")}
    for variant in VARIANTS:
        sub = df[df["variant"] == variant].sort_values("memory_mb")
        if not len(sub):
            continue
        x = sub["memory_mb"] + offsets[variant] * width
        b1 = ax.bar(x, sub["p50_ms"], width=width, color=colors[variant][0], label=f"{variant} p50")
        b2 = ax.bar(x + width, sub["p99_ms"], width=width, color=colors[variant][1], label=f"{variant} p99")
        ax.bar_label(b1, fmt="%.0f", fontsize=7, padding=2)
        ax.bar_label(b2, fmt="%.0f", fontsize=7, padding=2)
    ax.set_yscale("log")
    ax.set_xlabel("Lambda memory (MiB)")
    ax.set_ylabel("Response time (ms, log scale)")
    ax.set_title("User-facing latency (p50, p99) by memory allocation")
    ax.set_xticks(tiers)
    ax.legend(fontsize=8, ncol=2)
    top = ax.get_ylim()[1]
    ax.set_ylim(top=top * 2.5)  # headroom so the top row of labels doesn't clip
    fig.tight_layout()
    fig.savefig(FIGURES / "figure6_latency_vs_memory.png", dpi=150)
    plt.close(fig)
    print("  wrote figure5_billed_duration_vs_memory.png (ONNX only), figure6_latency_vs_memory.png (both, p50+p99, log scale)")


# ------------------------------------------------ Figure 7: tail latency ---

def figure7_tail_latency():
    """Report: 'derived from the steady traffic runs' - steady is the PRIMARY
    source, not a fallback."""
    print("\nFigure 7 - Tail latency (from steady traffic runs)")
    pct_cols = ["50%", "66%", "75%", "80%", "90%", "95%", "98%", "99%", "99.9%", "100%"]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    plotted = False
    for variant in VARIANTS:
        stats = (load_stats(f"steady_{variant}_p50_s10_run1")
                 or load_stats(f"steady_{variant}_p50_s5_run1")
                 or load_stats(f"steady_{variant}_p25_s5_run1"))
        if stats is None:
            print(f"  skip {variant}: no steady-traffic run1 stats found")
            continue
        vals = [stats.get(c) for c in pct_cols]
        if any(v is None for v in vals):
            continue
        ax.plot(pct_cols, vals, marker="o", label=variant)
        plotted = True
    if not plotted:
        print("  NO DATA")
        return
    ax.set_yscale("log")
    ax.set_xlabel("Percentile")
    ax.set_ylabel("Response time (ms, log scale)")
    ax.set_title("Tail latency percentile curve (steady traffic)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIGURES / "figure7_tail_latency.png", dpi=150)
    plt.close(fig)
    print("  wrote figure7_tail_latency.png")


# --------------------------------------------------- Figure 8: ramp-up -----

def figure8_ramp():
    print("\nFigure 8 - Cold-start ramp-up")
    for variant in VARIANTS:
        path = RAW / f"ramp_{variant}_0to20_stats_history.csv"
        if not path.exists():
            print(f"  skip {variant}: {path.name} not found")
            continue
        df = pd.read_csv(path)
        df = df[df["Name"].astype(str).str.strip() == "Aggregated"]
        if df.empty:
            continue
        t = df["Timestamp"] - df["Timestamp"].iloc[0]

        fig, axes = plt.subplots(3, 1, figsize=(8, 8), sharex=True)
        axes[0].plot(t, df["Requests/s"]); axes[0].set_ylabel("Requests/s")
        axes[0].set_title(f"Cold-start ramp-up - {variant}")
        axes[1].plot(t, df["50%"], label="p50"); axes[1].plot(t, df["95%"], label="p95")
        axes[1].set_ylabel("Response time (ms)"); axes[1].legend()
        if "User Count" in df.columns:
            axes[2].plot(t, df["User Count"])
        axes[2].set_ylabel("Active users"); axes[2].set_xlabel("Elapsed time (s)")
        fig.tight_layout()
        fig.savefig(FIGURES / f"figure8_ramp_{variant}.png", dpi=150)
        plt.close(fig)
        print(f"  wrote figure8_ramp_{variant}.png")


# ---------------------------------------------------- Figure 9: top-k ------

def figure9_topk():
    print("\nFigure 9 - top-k sweep (ONNX only)")
    files = sorted(RAW.glob("topk_onnx_*.csv"))
    if not files:
        print("  NO DATA")
        return
    df = pd.read_csv(files[-1])
    df = df[df["http_code"] == 200]
    if df.empty:
        print("  NO DATA (all requests failed)")
        return
    summary = df.groupby("k")["inference_ms"].agg(["mean", "std", "count"]).reset_index()
    save(summary, "figure9_topk")

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.errorbar(summary["k"], summary["mean"], yerr=summary["std"], marker="o", capsize=3)
    ax.set_xlabel("top_k"); ax.set_ylabel("Inference time (ms)")
    ax.set_title("Execution duration vs number of returned results (k)")
    fig.tight_layout()
    fig.savefig(FIGURES / "figure9_topk.png", dpi=150)
    plt.close(fig)
    print("  wrote figure9_topk.png")


# ----------------------------------------------- Table 9: cost analysis ----

# Rates exactly as listed in the report's Table 8
PRICING = {
    "AWS":   dict(gb_s=0.0000166667, per_inv=0.20e-6, free_gb_s_month=400_000, free_inv_month=1_000_000),
    "Azure": dict(gb_s=0.000016,     per_inv=0.20e-6, free_gb_s_month=400_000, free_inv_month=1_000_000),
    "GCP":   dict(gb_s=0.0000025,    per_inv=0.40e-6, free_gb_s_month=400_000, free_inv_month=2_000_000),
}
API_GW_PER_REQ = 1.00e-6  # $1 / million requests
# NOTE: Sec 7.1's exact wording is ambiguous ("...are excluded from all three
# for consistency") - could mean "excluded from Azure/GCP but kept for AWS"
# or "excluded from all three including AWS". Defaulting to the latter
# (cleanest reading of "for consistency" + "fair comparison" from Sec 7.1) -
# gateway cost is NOT added to any platform below. Flip ADD_GATEWAY_TO_AWS
# to True if your team intended the former reading.
ADD_GATEWAY_TO_AWS = False
EC2_6MO = round(0.0416 * 24 * 180, 2)  # matches report Eq. 2 exactly
MEMORY_MB = 3008
MONTHS = 6
DAYS = 30 * MONTHS


def table9_cost_analysis():
    """Report Eq. 1, applied to the SAME measured billed duration across all
    three FaaS platforms (their own methodology - not a real multi-cloud
    deployment). Representative billed duration comes from the ONNX
    framework-comparison runs (matches 'Lambda ONNX shown' in the report's
    own Table 9 note)."""
    print("\nTable 9 - Cost analysis")
    durations_ms = []
    for prefix in find_prefixes("framework_onnx_50users_run*"):
        cw = load_cloudwatch(prefix)
        if cw is not None:
            durations_ms.extend(cw["billed_duration_ms"].tolist())
    if not durations_ms:
        print("  skip: no billed_duration data (need framework_onnx_50users_run* collected)")
        return
    d_billed = sum(durations_ms) / len(durations_ms)
    print(f"  representative billed duration: {d_billed:.2f} ms "
          f"(mean of {len(durations_ms)} ONNX framework invocations)")

    traffics = {"1K req/day": 1_000, "10K req/day": 10_000,
                "100K req/day": 100_000, "1M req/day": 1_000_000}
    rows = []
    for label, per_day in traffics.items():
        total_req = per_day * DAYS
        gb_s_per_req = (d_billed / 1000.0) * (MEMORY_MB / 1024.0)
        row = {"Traffic": label}
        for platform, p in PRICING.items():
            total_gb_s = gb_s_per_req * total_req
            billable_gb_s = max(0.0, total_gb_s - p["free_gb_s_month"] * MONTHS)
            billable_inv = max(0, total_req - p["free_inv_month"] * MONTHS)
            cost = billable_gb_s * p["gb_s"] + billable_inv * p["per_inv"]
            if platform == "AWS" and ADD_GATEWAY_TO_AWS:
                cost += total_req * API_GW_PER_REQ
            row[platform] = round(cost, 2)
        row["EC2"] = EC2_6MO
        rows.append(row)
    save(pd.DataFrame(rows), "table9_cost_analysis")
    print(f"  (EC2 fixed cost per Eq. 2: ${EC2_6MO})")


# ------------------------------------------------------------------ main ---

def main():
    print(f"Reading from: {RAW}")
    print(f"Writing to:   {OUT}")

    table3_cold_start()
    table4_burst()
    table5_steady("onnx")
    table5_steady("pytorch")
    table6_burst_vs_steady()
    table7_input_size("onnx")
    figure4_framework()
    figures56_vertical_scaling()
    figure7_tail_latency()
    figure8_ramp()
    figure9_topk()
    table9_cost_analysis()

    print(f"\nDone. Tables in {TABLES}, figures in {FIGURES}")


if __name__ == "__main__":
    main()