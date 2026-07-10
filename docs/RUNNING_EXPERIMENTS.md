# Running the Experiment Campaign

Assumes the latest `main` (with `load_testing/`, `analysis/`, and
`ReservedConcurrentExecutions: 10` in `template.yaml`) is pulled on your laptop.

---

## The split: what runs where

| Where | What | Needs AWS credentials? |
|---|---|---|
| **EC2** | Locust, `curl` — sends load to the public API Gateway URL | No |
| **Laptop** | `sam deploy`, `pull_cloudwatch.py`, `collect_all.py` | Yes |

Your Learner Lab session must be **started (green)** for anything on the
laptop side. EC2 only needs the lab session running to *exist* — it stops when
the lab ends, and needs restarting from the console next time.

---

## Step 1 — Deploy the concurrency change (laptop, if not already done)

`ReservedConcurrentExecutions: 10` is a template-only change — no Docker
rebuild, no ECR push.

```bash
cd ~/Developer/minilm-lambda-eval
git pull origin main

# Confirm the account has headroom: reserving 10+10 needs unreserved
# concurrency to stay >= 100.
aws lambda get-account-settings --region us-east-1 \
  --query "AccountLimit.ConcurrentExecutions"

rm -rf .aws-sam
sam deploy --resolve-image-repos \
  --parameter-overrides "OnnxMemorySize=3008 PytorchMemorySize=3008"
```

Watch the changeset for `Modify` next to both `OnnxFunction` and
`PytorchFunction`. Then confirm it actually applied:

```bash
ONNX_FN=$(aws cloudformation describe-stack-resources --stack-name minilm-lambda-eval \
  --region us-east-1 --query "StackResources[?LogicalResourceId=='OnnxFunction'].PhysicalResourceId" --output text)
PT_FN=$(aws cloudformation describe-stack-resources --stack-name minilm-lambda-eval \
  --region us-east-1 --query "StackResources[?LogicalResourceId=='PytorchFunction'].PhysicalResourceId" --output text)

aws lambda get-function-concurrency --function-name "$ONNX_FN" --region us-east-1
aws lambda get-function-concurrency --function-name "$PT_FN"  --region us-east-1
```

Both must return `{"ReservedConcurrentExecutions": 10}`. **Save `$ONNX_FN` and
`$PT_FN`** — needed again in Step 8.

Skip this step in future sessions once confirmed deployed — only redo it if
`template.yaml` changes again (e.g. Test 7's memory sweep).

---

## Step 2 — Create the EC2 load generator (first time only)

A small instance in the **same region as the Lambdas** (`us-east-1`), used
purely to send HTTP load — it never calls an AWS API itself, so it needs no
IAM role at all.

1. Console → **EC2 → Launch instances**
2. **Name**: `locust-runner`
3. **AMI**: Amazon Linux 2023 (default, free-tier eligible)
4. **Instance type**: `t3.micro`
5. **Key pair**: *Proceed without a key pair* — connect via EC2 Instance
   Connect instead, no key management needed
6. **Network settings** → Edit:
   - Auto-assign public IP: **Enable**
   - Security group: add an inbound rule for **SSH (port 22)**, source
     **Anywhere (0.0.0.0/0)** — see note below for why
   - (leave everything else default — same VPC/subnet as the rest of the
     account, no need to create anything custom)
7. **Advanced details** → IAM instance profile: **None**
8. **Launch instance**

> **Why `0.0.0.0/0` and not "My IP"**: EC2 Instance Connect's browser-based
> "Connect using a Public IP" method doesn't SSH from your own laptop — it's
> proxied through AWS's own EC2 Instance Connect backend, which connects from
> AWS's IP ranges, not yours. A security rule scoped to "My IP" will reliably
> fail no matter how often it's re-matched to your current address, which is
> exactly what happened during initial setup. `0.0.0.0/0` is a reasonable
> tradeoff for a short-lived lab instance with no stored keys and no long-term
> data on it — not something to do on anything longer-lived or sensitive.

Wait for **2/2 status checks passed** (1-2 min) before connecting for the
first time.

### Bootstrap it

Connect: instance → **Connect** → **EC2 Instance Connect** tab → **Connect**
(username `ec2-user`, pre-filled).

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

This instance persists between sessions — you only do this once. It stops
automatically when the Learner Lab session ends and needs restarting (not
recreating) next time.

---

## Step 3 — Connect to EC2 (every session)

Console → **EC2 → Instances** → select `locust-runner`.

- **Stopped?** → Instance state → **Start instance**, wait for 2/2 status
  checks before connecting.
- **Running?** → Connect → **EC2 Instance Connect** tab → Connect.

---

## Step 4 — Every session, on EC2

```bash
cd ~/minilm-lambda-eval
git pull origin main
export PATH="$HOME/.local/bin:$PATH"
export HOST="https://1y6fpmdml3.execute-api.us-east-1.amazonaws.com"

# smoke test both endpoints before spending time on a full campaign
curl -s -X POST "$HOST/onnx/search"    -H 'Content-Type: application/json' -d '{"query":"test","top_k":5}' | head -c 120; echo
curl -s -X POST "$HOST/pytorch/search" -H 'Content-Type: application/json' -d '{"query":"test","top_k":5}' | head -c 120; echo
```

`$HOST` is the **base URL only** — the scripts append `/onnx/search` or
`/pytorch/search` themselves.

Campaigns outlive a browser tab. Run them under `tmux`:

```bash
sudo dnf install -y tmux   # first time only
tmux new -s exp
# ... run a long test ...
# detach: Ctrl-b then d       reattach later: tmux attach -t exp
```

---

## Step 5 — Run the tests, in order

### Test 1 — Cold start (Table 3)

Run **first**, while the system is genuinely idle. Slowest test by far — start
it and walk away.

```bash
./load_testing/cold_start_test.sh onnx    10 900   # ~2.5 h
./load_testing/cold_start_test.sh pytorch 10 900   # ~2.5 h
```

(`900` = 15 min gaps, matching the report's stated methodology. Note in your
report if you use a shorter gap.)

### Test 7 — Vertical scaling (Figures 5, 6)

Do this before the bulk tests — it fixes the memory tier the rest of the
campaign runs at. Needs laptop/EC2 ping-pong, since changing memory means
redeploying.

```
LAPTOP:  sam deploy --resolve-image-repos --parameter-overrides "OnnxMemorySize=1024 PytorchMemorySize=1024"
EC2:     ./load_testing/experiments/test07_vertical_scaling.sh 1024

LAPTOP:  sam deploy --resolve-image-repos --parameter-overrides "OnnxMemorySize=2048 PytorchMemorySize=2048"
EC2:     ./load_testing/experiments/test07_vertical_scaling.sh 2048

LAPTOP:  sam deploy --resolve-image-repos --parameter-overrides "OnnxMemorySize=3008 PytorchMemorySize=3008"
EC2:     ./load_testing/experiments/test07_vertical_scaling.sh 3008
```

The number passed on EC2 only **labels** output files — it doesn't change
anything on AWS. Verify the real deployed value before each run:

```bash
aws lambda get-function-configuration --function-name "$ONNX_FN" \
  --query MemorySize --region us-east-1
```

`template.yaml`'s own comments warn ONNX **times out at 1024 MB on a cold
start** (Lambda scales vCPU with memory). The script warms both endpoints
first, so warm invocations should be fine — expect cold-start failures at the
lowest tier; that's a real result, not a broken run.

**Finish on 3008** so the rest of the campaign matches the report's stated
default memory.

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

Table 5 is ONNX-only in the report, but run PyTorch too — see the
interpretation note below, the contrast is one of the stronger findings.

### Test 9 — Cold-start ramp (Figure 8)

Needs a **cold** function. Leave endpoints idle ~15 min first, or run at the
very start of a session.

```bash
./load_testing/experiments/test09_ramp.sh onnx      # ~7 min
# wait ~15 min for pytorch to go cold again
./load_testing/experiments/test09_ramp.sh pytorch   # ~7 min
```

Deliverable: the per-second series in `*_stats_history.csv` (`Timestamp`,
`User Count`, `Requests/s`, `50%`, `95%`) — plot the three panels stacked.

### Test 10 — top-k sweep (Figure 9)

No Locust, no CloudWatch — reads `inference_ms` straight from the response.

```bash
./load_testing/experiments/test10_topk.sh onnx      # ~3 min
```

### Tests 4 and 8 — no new runs

Test 4 (burst vs steady, Table 6) is a comparison table from Tests 2 and 3.
Test 8 (tail latency, Figure 7) replots percentile columns already in Test 3's
`*_stats.csv`.

---

## Step 6 — Get the data back to your laptop

Each run in `data/raw/` produces:

| File | Contents |
|---|---|
| `<name>_stats.csv` | Summary: counts, failures, p50…p100 |
| `<name>_stats_history.csv` | Per-second time series (Figures 1–3, 8) |
| `<name>_failures.csv` | Every failed request |
| `<name>_window.json` | UTC start/end for CloudWatch correlation |

From EC2:

```bash
cd ~/minilm-lambda-eval
git add -f data/raw            # -f because .gitignore excludes it
git commit -m "Raw experiment data: <which tests>"
git push origin main
```

---

## Step 7 — Pull CloudWatch and correlate (laptop)

Learner Lab session started, fresh credentials, then:

```bash
cd ~/Developer/minilm-lambda-eval
git pull origin main

python3 analysis/collect_all.py
```

Walks every `*_window.json`, resolves the right Lambda function from the
`variant` field, writes a matching `*_cloudwatch.csv` next to each. Skips ones
already pulled — safe to re-run as more data arrives. `--force` re-pulls,
`--pattern burst_onnx` targets a subset.

Single run with a printed summary:

```bash
python3 analysis/pull_cloudwatch.py \
  --window data/raw/burst_onnx_n10_run1_window.json \
  --function "$ONNX_FN"
```

Each `*_cloudwatch.csv`: `timestamp_utc, duration_ms, billed_duration_ms,
memory_size_mb, max_memory_used_mb, init_duration_ms, cold_start` — one row per
invocation. Maps onto the report as:

- **MinT/AvgT/MaxT** → min/mean/max of `duration_ms`
- **InitDuration** (Table 3) → `init_duration_ms` where `cold_start == 1`
- **MaxMem** → max of `max_memory_used_mb`
- **BilledDuration** (cost analysis) → `billed_duration_ms`
- **N. Conc. Execs/Invocations/Throttles/Errors** → printed summary
- **Fail%/CliT/p50/p95/p99** → Locust's `*_stats.csv`, not CloudWatch

CloudWatch log ingestion lags a few seconds — the puller already widens the
query ±30s. If a pull returns 0 rows right after a run, wait 30s and retry.

---

## Interpreting the results

**Burst is where the concurrency limit bites, not steady.** Concurrency ≈
arrival rate × duration. ONNX warm at ~25ms serving 50 req/s steady needs only
~1.3 concurrent containers — nowhere near 10, so expect **zero throttling**
there. A *burst* of 50 wants 50 containers at once; 40 get throttled. If
steady-50 is clean while burst-50 fails, that's correct, and it's exactly
Table 6's point.

**The two variants diverge sharply under sustained load.** PyTorch at ~700ms
needs ~35 concurrent to sustain 50 req/s — far over the limit — so it
throttles heavily where ONNX barely registers. Report AvgT of *successful*
invocations alongside failure rate: CloudWatch `Duration` only counts
invocations that actually ran, so low AvgT next to a high failure rate isn't a
contradiction.

**Some report predictions may not survive contact with data.** Treat Section
6's stated outcomes as hypotheses. If reality differs, change the conclusion,
not the data.

---

## Housekeeping

- **Stop the EC2 instance** when not testing.
- **Don't raise the user cap above 50** — matches the project brief's "do not
  generate too heavy a load," and Learner Lab abuse detection is real.
- **Only point Locust at your own API Gateway.**
- **Log each campaign** in the shared sheet: test name, date, memory tier,
  anything unusual. `_window.json` records timestamps but not *configuration*.
