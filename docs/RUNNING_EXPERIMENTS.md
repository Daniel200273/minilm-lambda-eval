# Running the Experiment Campaign

Load is generated from a **t3.micro EC2 instance in `us-east-1`** (same region as
the Lambdas) to remove home-network variability, matching the methodology in the
report. Metrics are pulled **from your laptop**, because that is where AWS
credentials live.

---

## The split: what runs where

| Where | What | Needs AWS credentials? |
|---|---|---|
| **EC2** | Locust, `curl` — sends load to the public API Gateway URL | No |
| **Laptop** | `sam deploy`, `pull_cloudwatch.py`, `collect_all.py` | Yes |

The endpoints have no authentication, so EC2 only needs internet access. It never
calls an AWS API. That is why the instance is launched with **no IAM instance
profile** — nothing to attach, nothing to leak.

Your Learner Lab session must be **started (green)** whenever you run anything on
the laptop side. The EC2 instance itself only needs the lab running to *exist* —
it stops when the lab session ends.

---

## Part 0 — Deploy the concurrency change (laptop, once)

`ReservedConcurrentExecutions: 10` is a template change only. No Docker rebuild,
no ECR push.

```bash
# Check the account has headroom first: reserving 10+10 requires
# unreserved concurrency to stay >= 100.
aws lambda get-account-settings --region us-east-1 \
  --query "AccountLimit.ConcurrentExecutions"

cd ~/Developer/minilm-lambda-eval
rm -rf .aws-sam
sam deploy --resolve-image-repos \
  --parameter-overrides "OnnxMemorySize=3008 PytorchMemorySize=3008"
```

Confirm it applied:

```bash
ONNX_FN=$(aws cloudformation describe-stack-resources --stack-name minilm-lambda-eval \
  --region us-east-1 --query "StackResources[?LogicalResourceId=='OnnxFunction'].PhysicalResourceId" --output text)
PT_FN=$(aws cloudformation describe-stack-resources --stack-name minilm-lambda-eval \
  --region us-east-1 --query "StackResources[?LogicalResourceId=='PytorchFunction'].PhysicalResourceId" --output text)

aws lambda get-function-concurrency --function-name "$ONNX_FN" --region us-east-1
aws lambda get-function-concurrency --function-name "$PT_FN"  --region us-east-1
```

Both must return `{"ReservedConcurrentExecutions": 10}`. Save `$ONNX_FN` and
`$PT_FN` — you need them for the analysis step.

---

## Part 1 — Commit the scripts (laptop, once)

Drop the downloaded files into the repo, then:

```bash
cd ~/Developer/minilm-lambda-eval
chmod +x load_testing/*.sh load_testing/experiments/*.sh
git add load_testing analysis
git commit -m "Add Locust experiment drivers and CloudWatch collectors"
git push origin main
```

Also add this to `.gitignore` so raw CSVs don't bloat the repo until you decide
to commit them deliberately:

```
data/raw/
```

---

## Part 2 — Launch the EC2 instance (console, once)

1. AWS Console → **EC2** → **Launch instances**
2. **Name**: `locust-runner`
3. **AMI**: Amazon Linux 2023 (default, free-tier eligible)
4. **Instance type**: `t3.micro`
5. **Key pair**: *Proceed without a key pair* — you'll use EC2 Instance Connect
6. **Network settings** → Edit:
   - Auto-assign public IP: **Enable**
   - Security group: allow **SSH (22)** from **My IP**
7. **Advanced** → IAM instance profile: **None**
8. **Launch instance**

Connect: select the instance → **Connect** → **EC2 Instance Connect** tab →
**Connect**. A browser terminal opens.

> **The instance stops when your Learner Lab session ends.** Restart it from the
> console next session (Instances → select → Instance state → Start). Its disk
> and everything you installed persists; only the public IP changes.

---

## Part 3 — Bootstrap the instance (EC2, once)

```bash
sudo dnf install -y git
git clone https://github.com/Daniel200273/minilm-lambda-eval.git
cd minilm-lambda-eval
chmod +x load_testing/*.sh load_testing/experiments/*.sh
./load_testing/setup_ec2.sh
source ~/.bashrc
```

Verify:

```bash
locust --version
```

---

## Part 4 — Every session on EC2

```bash
cd ~/minilm-lambda-eval
git pull origin main
export PATH="$HOME/.local/bin:$PATH"
export HOST="https://1y6fpmdml3.execute-api.us-east-1.amazonaws.com"

# smoke test both endpoints before spending time on a campaign
curl -s -X POST "$HOST/onnx/search"    -H 'Content-Type: application/json' -d '{"query":"test","top_k":5}' | head -c 120; echo
curl -s -X POST "$HOST/pytorch/search" -H 'Content-Type: application/json' -d '{"query":"test","top_k":5}' | head -c 120; echo
```

`$HOST` is the **base URL, no path** — the scripts append `/onnx/search` or
`/pytorch/search` themselves.

Long campaigns outlive a browser tab. Run them under `tmux`:

```bash
sudo dnf install -y tmux
tmux new -s exp
# ... start a long test ...
# detach: Ctrl-b then d
# reattach later: tmux attach -t exp
```

---

## Part 5 — Run the tests, in order

### Test 1 — Cold start (Table 3)

Must run **first**, on a genuinely idle system. Slowest test by far.

```bash
./load_testing/cold_start_test.sh onnx    10 900   # ~2.5 h
./load_testing/cold_start_test.sh pytorch 10 900   # ~2.5 h
```

Use `300` instead of `900` if you're short on lab time — but **say which you used
in the report**, since AWS's container reclamation window is undocumented and
variable, and 5 minutes may not always guarantee a cold container.

Start this in `tmux` and go do something else.

### Test 7 — Vertical scaling (Figures 5, 6)

Do this **before** the bulk tests, because it determines the memory tier
everything else runs at. It needs laptop/EC2 ping-pong, because changing memory
means redeploying.

```
LAPTOP:  sam deploy --resolve-image-repos --parameter-overrides "OnnxMemorySize=1024 PytorchMemorySize=1024"
EC2:     ./load_testing/experiments/test07_vertical_scaling.sh 1024

LAPTOP:  sam deploy --resolve-image-repos --parameter-overrides "OnnxMemorySize=2048 PytorchMemorySize=2048"
EC2:     ./load_testing/experiments/test07_vertical_scaling.sh 2048

LAPTOP:  sam deploy --resolve-image-repos --parameter-overrides "OnnxMemorySize=3008 PytorchMemorySize=3008"
EC2:     ./load_testing/experiments/test07_vertical_scaling.sh 3008
```

The `1024` / `2048` / `3008` argument on EC2 only **labels** the output files. It
does not change anything on AWS. Passing the wrong number silently mislabels your
data, so verify the deployed value first:

```bash
aws lambda get-function-configuration --function-name "$ONNX_FN" \
  --query MemorySize --region us-east-1
```

Your `template.yaml` comments already warn that ONNX **times out at 1024 MB on a
cold start** (Lambda scales vCPU with memory). The script warms both endpoints
before measuring, so warm invocations should be fine — but expect cold-start
failures at the lowest tier. That is a legitimate result, not a broken run.

Finish on `3008` so the rest of the campaign matches the report's stated default.

### Tests 2, 5, 6 — Burst, input size, framework (Tables 4, 7; Figure 4)

```bash
./load_testing/experiments/test02_burst.sh          # both variants, ~25 min
./load_testing/experiments/test05_input_size.sh     # onnx, ~15 min
./load_testing/experiments/test06_framework.sh      # both variants, ~20 min
```

### Test 3 — Steady traffic (Table 5)

```bash
./load_testing/experiments/test03_steady.sh onnx     # ~20 min
./load_testing/experiments/test03_steady.sh pytorch  # ~20 min
```

Table 5 is ONNX-only in the report, but run PyTorch too — see the interpretation
note below, the contrast is one of your better findings.

### Test 9 — Cold-start ramp (Figure 8)

Needs a **cold** function. Leave the endpoints idle ~15 minutes first, or run it
at the very start of a session.

```bash
./load_testing/experiments/test09_ramp.sh onnx      # ~7 min
# wait ~15 min for pytorch to go cold again
./load_testing/experiments/test09_ramp.sh pytorch   # ~7 min
```

The deliverable is the per-second time series in `*_stats_history.csv`
(`Timestamp`, `User Count`, `Requests/s`, `50%`, `95%`) — plot those three panels
stacked.

### Test 10 — top-k sweep (Figure 9)

No Locust, no CloudWatch. Reads `inference_ms` straight from the response body.

```bash
./load_testing/experiments/test10_topk.sh onnx      # ~3 min
```

### Tests 4 and 8 — no new runs

Test 4 (burst vs steady, Table 6) is a comparison table built from Tests 2 and 3.
Test 8 (tail latency, Figure 7) replots percentile columns already present in
Test 3's `*_stats.csv`.

---

## Part 6 — Get the data back to your laptop

Everything lands in `data/raw/` on EC2. Each run produces:

| File | Contents |
|---|---|
| `<name>_stats.csv` | Summary: counts, failures, p50…p100 |
| `<name>_stats_history.csv` | Per-second time series (needed for Figures 1–3, 8) |
| `<name>_failures.csv` | Every failed request |
| `<name>_window.json` | UTC start/end — how CloudWatch data gets matched |

From EC2, commit them:

```bash
cd ~/minilm-lambda-eval
git add -f data/raw            # -f because .gitignore excludes it
git commit -m "Raw experiment data: <which tests>"
git push origin main
```

They're small text CSVs — a full campaign is a few MB. If you'd rather not commit
them, `tar czf raw.tgz data/raw` and download via the console.

---

## Part 7 — Pull CloudWatch and correlate (laptop)

Start the Learner Lab, refresh `~/.aws/credentials`, then:

```bash
cd ~/Developer/minilm-lambda-eval
git pull origin main

python3 analysis/collect_all.py
```

`collect_all.py` walks every `*_window.json`, resolves the right Lambda function
from the `variant` field via CloudFormation, and writes a matching
`*_cloudwatch.csv` next to each one. It skips windows already pulled, so it's safe
to re-run as more data arrives. Use `--force` to re-pull, `--pattern burst_onnx`
to target a subset.

For a single run with a printed summary:

```bash
python3 analysis/pull_cloudwatch.py \
  --window data/raw/burst_onnx_n10_run1_window.json \
  --function "$ONNX_FN"
```

Each `*_cloudwatch.csv` has one row per Lambda invocation:
`timestamp_utc, duration_ms, billed_duration_ms, memory_size_mb,
max_memory_used_mb, init_duration_ms, cold_start`.

That maps onto the report's metrics as:

- **MinT / AvgT / MaxT** → min/mean/max of `duration_ms`
- **InitDuration** (Table 3) → `init_duration_ms` where `cold_start == 1`
- **MaxMem** → max of `max_memory_used_mb`
- **BilledDuration** (cost analysis) → `billed_duration_ms`
- **N. Conc. Execs / Invocations / Throttles / Errors** → printed summary, or
  CloudWatch Metrics directly

Client-side columns (**Fail%**, **CliT**, **p50/p95/p99**) come from Locust's
`*_stats.csv`.

> CloudWatch log ingestion lags a few seconds behind the invocation. The puller
> already widens the query by ±30 s to compensate. If a pull returns 0 rows
> immediately after a run, wait 30 seconds and retry before assuming something
> broke.

---

## Interpreting the results — three things to expect

**1. Burst is where the concurrency limit bites, not steady.**
Concurrency ≈ arrival rate × duration. At 50 req/s steady with ONNX warm at
~25 ms, that's only ~1.3 concurrent containers — nowhere near the limit of 10, so
you may see **zero throttling**. But a *burst* of 50 simultaneous requests wants
50 containers at once, and 40 get throttled. If steady-50 shows no failures while
burst-50 shows many, that is correct behaviour, and it's exactly the burst-vs-
steady insight Table 6 is designed to surface.

**2. The two variants will diverge sharply under sustained load.**
PyTorch at ~700 ms warm needs ~35 concurrent containers to sustain 50 req/s — far
over the limit of 10 — so it will throttle heavily where ONNX barely registers.
Report the average duration of *successful* invocations alongside the failure
rate: CloudWatch `Duration` only counts invocations that actually ran, so a low
AvgT next to a high failure rate is not a contradiction.

**3. Some report predictions may not survive contact with data.**
Section 6 and the Conclusion are currently written as if the outcomes are known.
Treat them as hypotheses. If PyTorch turns out *less* memory-sensitive than
predicted, or the cold-start gap is smaller than expected, change the conclusion —
don't reshape the data. Tell your teammates this too, so nobody feels locked into
the draft's predictions.

---

## Housekeeping

- **Stop the EC2 instance** when not testing. It's free-tier eligible, but the
  habit protects your $50.
- **Cap concurrency.** The scripts top out at 50 users. Don't raise it — the
  project brief says "do not generate too heavy a load," and Learner Lab abuse
  detection is real.
- **Never point Locust at anything but your own API Gateway.**
- **Log each campaign** in the shared sheet: test name, date, deployed memory,
  reserved concurrency, and anything unusual. The `_window.json` files record the
  timestamps for you, but not the *configuration* — and in three weeks nobody will
  remember which memory tier a given run used.
