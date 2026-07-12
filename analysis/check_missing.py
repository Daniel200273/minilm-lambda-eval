#!/usr/bin/env python3
"""
Lists the EXACT missing runs for each test - not just a count, the specific
(variant, N, rep) / (variant, config, rep) combinations still needed.

A run is considered "done" if its _stats.csv (or, for cold_start/topk, its
main result file) exists in data/raw/ - that's written the moment a single
run_experiment.sh call finishes, so it's a reliable completion signal
independent of whether collect_all.py has run yet.

Usage:
    python3 analysis/check_missing.py            # everything
    python3 analysis/check_missing.py burst       # just one test
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW = REPO_ROOT / "data" / "raw"

VARIANTS = ["onnx", "pytorch"]


def exists(prefix):
    return (RAW / f"{prefix}_stats.csv").exists()


def report(name, missing, total):
    done = total - len(missing)
    if not missing:
        print(f"{name}: COMPLETE ({done}/{total})")
        return
    print(f"{name}: {done}/{total} done, {len(missing)} MISSING")
    for m in missing:
        print(f"    {m}")


def check_burst():
    missing = []
    total = 0
    for variant in VARIANTS:
        for n in [1, 5, 10, 15, 25, 50]:
            for rep in range(1, 6):
                total += 1
                prefix = f"burst_{variant}_n{n}_run{rep}"
                if not exists(prefix):
                    missing.append(prefix)
    report("burst", missing, total)


def check_steady():
    missing = []
    total = 0
    for variant in VARIANTS:
        for peak, step in [(25, 5), (50, 10), (50, 5)]:
            for rep in range(1, 6):
                total += 1
                prefix = f"steady_{variant}_p{peak}_s{step}_run{rep}"
                if not exists(prefix):
                    missing.append(prefix)
    report("steady", missing, total)


def check_inputsize():
    missing = []
    total = 0
    for bucket in ["short", "medium", "long"]:
        for n in [1, 10, 15]:
            for rep in range(1, 6):
                total += 1
                prefix = f"inputsize_onnx_{bucket}_n{n}_run{rep}"
                if not exists(prefix):
                    missing.append(prefix)
    report("inputsize", missing, total)


def check_framework():
    missing = []
    total = 0
    for variant in VARIANTS:
        for rep in range(1, 4):
            total += 1
            prefix = f"framework_{variant}_50users_run{rep}"
            if not exists(prefix):
                missing.append(prefix)
    report("framework", missing, total)


def check_vscale():
    missing = []
    total = 0
    for variant in VARIANTS:
        for mem in [1024, 2048, 3008]:
            for rep in range(1, 4):
                total += 1
                prefix = f"vscale_{variant}_mem{mem}_run{rep}"
                if not exists(prefix):
                    missing.append(prefix)
    report("vscale", missing, total)


def check_ramp():
    missing = []
    total = 0
    for variant in VARIANTS:
        total += 1
        prefix = f"ramp_{variant}_0to20"
        if not exists(prefix):
            missing.append(prefix)
    report("ramp", missing, total)


def check_cold_start():
    missing = []
    total = 0
    for variant in VARIANTS:
        total += 1
        files = [f for f in RAW.glob(f"cold_start_{variant}_*.csv")
                 if "_window" not in f.stem and "_cloudwatch" not in f.stem]
        if not files:
            missing.append(f"cold_start_{variant}_* (no run found at all)")
    report("cold_start", missing, total)


def check_topk():
    total = 1
    files = list(RAW.glob("topk_onnx_*.csv"))
    missing = [] if files else ["topk_onnx_* (no run found at all)"]
    report("topk", missing, total)


CHECKS = {
    "cold_start": check_cold_start,
    "burst": check_burst,
    "steady": check_steady,
    "inputsize": check_inputsize,
    "framework": check_framework,
    "vscale": check_vscale,
    "ramp": check_ramp,
    "topk": check_topk,
}


def main():
    if not RAW.exists():
        sys.exit(f"No such directory: {RAW}")

    which = sys.argv[1] if len(sys.argv) > 1 else None
    if which:
        if which not in CHECKS:
            sys.exit(f"Unknown test '{which}'. Choose from: {', '.join(CHECKS)}")
        CHECKS[which]()
    else:
        for fn in CHECKS.values():
            fn()
            print()


if __name__ == "__main__":
    main()
