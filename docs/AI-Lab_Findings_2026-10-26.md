# AI-Lab: Local Coding Agent — Experimental Findings

**Report date:** October 26, 2026 (America/Chicago)  
**Status:** Working local agent; Q8 optimization validated; reasoning-mode comparison preliminary  
**Scope:** Observations from terminal output supplied during the experiments. This document is not an independent reproduction of those runs.

## Executive summary

A local coding assistant was assembled on an RTX 3070 Ti workstation using **Pi 1.4.0**, **Ollama 0.40.11**, and **Qwen3.5 9B Q4_K_M** with a **16,384-token context window**. The coding agent can inspect files, edit code, run tests, and iterate. A synthetic Python Expense Tracker repair benchmark reached **26/26 independent acceptance tests** with reasoning enabled. Switching Ollama's KV cache from FP16 to Q8_0 reduced the reported KV-cache allocation from **512 MiB to 272 MiB** and increased measured generation throughput on a fixed binary-search prompt from **36.46 to 59.83 tokens/s** (three runs per condition). Under Q8, an independent coding-agent attempt finished in **56.04 seconds** with 26/26 tests passing; another succeeded in **85.21 seconds**.

Turning model reasoning off dramatically reduced latency on short direct prompts, but in one isolated Expense Tracker attempt it passed only **23/26** acceptance tests in **48.97 seconds**. The three failing tests were all attributable to one remaining monthly-reporting defect: grouping by `%m` instead of `%Y-%m`. Consequently, reasoning-enabled Pi remains the preferred default for autonomous multi-step repair, while `localcode-fast` is useful for low-risk, straightforward tasks. More repetitions and representative workloads are needed before generalizing these observations.

## 1. Test workstation and software

| Component | Configuration observed/reported |
|---|---|
| Operating system | Ubuntu 24.04.5 LTS on a separate SSD |
| CPU | AMD Ryzen 5 5600X (6 cores / 12 threads) |
| RAM | 32 GB DDR4 |
| GPU | NVIDIA GeForce RTX 3070 Ti, 8 GB VRAM |
| NVIDIA driver | 595.99.02 (CUDA capability reported as 13.2) |
| Ollama | 0.40.11 |
| Agent | Pi 1.4.0 |
| Main inference model | `pi-qwen35-9b-16k:latest`, derived from Qwen3.5 9B Q4_K_M |
| Context | 16,384 tokens |
| Agent-side model identifier | `pi-qwen35-9b-16k` |
| Inference endpoint | Ollama OpenAI-compatible `/v1/chat/completions` |
| Inference price | Locally hosted; no cloud inference API charges |

Installed model tags observed: `pi-qwen35-9b-32k:latest`, `pi-qwen35-9b-16k:latest`, `qwen3.5:9b-q4_K_M`, `qwen3:8b-32k`, `qwen3:8b`.

**Environment note:** The separate Ubuntu SSD and the Windows installation are independent; this project did not require modifying the Windows installation.

## 2. Architecture, paths, and operational workflow

### Everyday agent

```text
Developer terminal (project directory)
     -> ~/.local/bin/localcode [or localcode-fast]
     -> Pi 1.4.0 (Node.js v24.22.1 via nvm)
     -> Ollama at 127.0.0.1:11434/v1
     -> pi-qwen35-9b-16k (Qwen3.5 9B, 16K)
     -> project files, shell commands, tests
```

| Item | Path / detail |
|---|---|
| Project repository | `~/AI-Lab/` |
| Regular Pi config | `~/AI-Lab/daily-agent/models.json` |
| Fast Pi config | `~/AI-Lab/daily-agent-fast/models.json` |
| Regular launcher | `~/.local/bin/localcode` |
| Fast launcher | `~/.local/bin/localcode-fast` |
| Benchmark | `~/AI-Lab/benchmarks/coding-tasks/expense-tracker/` |
| Benchmark Pi config | `configs/pi-models.json` (relative to benchmark root) |
| Benchmark runner | `runner.py` |
| Restricted bridge | `security/bridge.py` |
| Attempt results | `attempts/<attempt-name>/result.json` |

The launcher exports `PATH` to include `~/.nvm/versions/node/v24.22.1/bin` and sets `PI_CODING_AGENT_DIR` to the relevant configuration directory, then runs Pi with `--offline --provider ollama --model pi-qwen35-9b-16k`.

**Security distinction:** The everyday agent operates with the user's usual Linux account permissions and is **not automatically sandboxed**. The synthetic benchmark, in contrast, uses a restricted Bubblewrap environment and a narrowly scoped inference bridge. Running Pi inside disposable Git repositories and reviewing diffs remains advisable for everyday use.

### Benchmark isolation

The dedicated benchmark runner establishes a fresh `/work` directory, dedicated agent state, and a Unix-socket connection to a broker. It uses a root-owned Bubblewrap launcher at `/usr/local/libexec/ai-lab-expense-bwrap`, a specific AppArmor profile, restricted filesystem mounts, no direct network access for the agent, and a broker allowing only approved local Ollama requests. Security/preflight testing reportedly passed **32/32** in an offline mock-upstream run. Agent sandbox `PATH` is `/usr/bin:/bin`, so the benchmark invokes the installed Node binary and Pi JavaScript entrypoint by absolute path.

**Broker request constraint:** The bridge initially rejected an added `reasoning_effort` field with HTTP 403. The allowlist was subsequently expanded narrowly to accept `reasoning_effort` **only if its value is `"none"`**. This does not change the intended filesystem/process/network restrictions. The benchmark model config was restored after the experimental run, and the original baseline should remain distinct from fast-mode settings.

## 3. Initial bring-up and baseline behavior

1. **Qwen3 8B / Codex:** At 4K context, an early Qwen3 8B run reached about **83.80 tokens/s** with full GPU residency, but an oversized Codex prompt was truncated, making the setup unsuitable for the requested workflow. A 32K-context alias ran with partial CPU offloading at about **14.87 tokens/s**; a repository-inspection task completed in **319 s**. The original bwrap/AppArmor user-namespace failure was addressed with an exact-path AppArmor rule instead of disabling protections globally.
2. **Pi / Qwen3.5 9B:** A simpler repository-inspection trial at 16K recorded **35.06 s median**, **34.4 tokens/s**, roughly **6,934 MiB VRAM** and **30/33 layers on GPU** in that earlier environment. A 32K trial recorded **73.31 s**, **18.88 tokens/s**, roughly **7,048 MiB VRAM** and **26/33 layers on GPU**. These are different workloads and contexts; do not compare their absolute times causally.
3. **Expense Tracker first success (`pi-06`):** Correct Pi model identifier, explicit `--provider ollama`, and known-working CLI flags were restored; the bridge upstream timeout was extended from 30 s to 120 s. The task completed in **104.74 s**, with **26/26 independent regression tests passing**, exit code 0, and no timeout. Six observed inference streams ended with completion markers.
4. **Everyday smoke test:** Pi successfully read the `AI-Lab` repository and created a basic Python CLI calculator plus unit tests. The calculator exercise finished with **6/6 tests passing**, though the agent had initially written an incorrect negative-zero test and then corrected it. This was a basic workflow smoke test, not a complex coding benchmark.

## 4. Flash Attention and Q8 KV-cache optimization

### Setting verification

Ollama's service originally had no explicit optimization override. Its logs nevertheless stated **`Flash Attention enabled`** with `flash_attn = auto`. It was therefore unnecessary to force Flash Attention on.

The initial KV cache was FP16:

```text
llama_kv_cache: size = 512.00 MiB (16384 cells, 8 layers)
K (f16): 256.00 MiB, V (f16): 256.00 MiB
```

A systemd drop-in at `/etc/systemd/system/ollama.service.d/10-kv-cache.conf` added:

```ini
[Service]
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
```

After a daemon reload and Ollama restart, logs showed:

```text
llama_kv_cache: size = 272.00 MiB (16384 cells, 8 layers)
K (q8_0): 136.00 MiB, V (q8_0): 136.00 MiB
```

`ollama ps` displayed **84% GPU / 16% CPU** under FP16 and **88% GPU / 12% CPU** under Q8. This percentage is an aggregate placement indicator, **not** a direct count of layers. The 240 MiB KV allocation reduction and placement shift are observed; the precise mechanism driving speed gains has not been isolated.

### Controlled prompt throughput

Conditions: same model tag, 16K context, binary-search code/explanation prompt, `num_predict=512`, `temperature=0`, `seed=42`; direct Ollama `/api/generate`. Each request hit the 512-token generation cap. Speeds are generated tokens divided by Ollama `eval_duration` and exclude model-loading and prompt-processing time.

| Run | FP16 tokens/s | Q8_0 tokens/s |
|---:|---:|---:|
| 1 | 36.32 | 58.28 |
| 2 | 36.22 | 60.59 |
| 3 | 36.85 | 60.62 |
| **Arithmetic mean** | **36.46** | **59.83** |

**Observed differences:** KV-cache allocation **512 → 272 MiB** (**−46.9%**); throughput **36.46 → 59.83 tokens/s** (**+64.1%** for this prompt). This is a useful A/B comparison under two configurations, though the number of repetitions is small, and run order, thermals, clocks, and content length could influence measurements.

### Autonomous coding benchmark: Q8

| Attempt | Configuration at run time | Elapsed | Tests | Exit | Timeout |
|---|---|---:|---:|---:|---|
| `pi-06` | Pre-Q8 FP16 baseline | 104.74 s | 26/26 | 0 | No |
| `pi-q8-01` | Q8 cache; standard Pi reasoning behavior | 56.04 s | 26/26 | 0 | No |
| `pi-q8-fast-01` | Q8 cache; **original benchmark config** despite its name | 85.21 s | 26/26 | 0 | No |

The second run named `fast` was launched *before* the benchmark model config was modified; **it must not be counted as a non-thinking run**. Agent wall-clock timings are not a clean inference-only comparison: tool-call count, content, decisions, filesystem operations, and output tokens vary from run to run. Both Q8 standard-behavior runs nonetheless passed all 26 tests.

## 5. Reasoning vs. non-thinking mode

### API mechanism and model behavior

The Qwen3.5 model's Modelfile includes `RENDERER qwen3.5`, `PARSER qwen3.5`, and `PARAMETER num_ctx 16384`; its template is `{{ .Prompt }}`. Ollama's **native `/api/chat`** endpoint accepted `"think": false`, and its **OpenAI-compatible `/v1/chat/completions`** endpoint accepted `"reasoning_effort": "none"`.

A separate Pi model config in `~/AI-Lab/daily-agent-fast/models.json` adds:

```json
"samplingParams": {
  "temperature": 0,
  "seed": 42,
  "reasoning_effort": "none"
}
```

Pi 1.4.0 source inspection showed `resolveSamplingParams` merges model-level sampling parameters into outgoing options. A `localcode-fast --no-tools --mode json --print` greeting produced **3 output tokens, 0 reported reasoning tokens, `stop`**, and the response `Hello!`. Its successful code-inspection smoke test read `calculator.py` and `test_calculator.py` without requested edits, although some suggestions were imprecise.

### Short-prompt tests

| Test | Thinking enabled | Thinking disabled |
|---|---:|---:|
| Greeting, native API | 38.91 s; 2,048 tokens; `length`; **no final answer** | 0.38 s; 10 tokens; complete answer |
| `is_prime(n)` generation, native API | 31.58 s; 1,716 tokens | 3.16 s; 157 tokens |
| `is_prime(n)` independent cases | **19/19** in 32.12 s | **19/19** in 2.99 s |
| Greeting, OpenAI-compatible API | 8.94 s; 512 tokens; `length`; **no final answer** (`high`) | 0.27 s; 10 tokens; complete answer (`none`) |

These show strong token/latency savings for **simple prompts** with thinking disabled. They do not establish that non-thinking performs equally well on autonomous multi-step software engineering.

### Non-thinking Expense Tracker run

The initial `pi-q8-nothink-01` failed in **0.92 s**, leaving **15/26** tests passing: the restricted bridge did not yet allow the `reasoning_effort` request field. **This is an infrastructure/configuration failure, not a model-quality result.**

The broker was updated to allow `reasoning_effort` only with the value `"none"`. Local authorization tests confirmed acceptance of `"none"` and rejection of `"high"` and the invalid value `123`. The modified benchmark config then produced a genuine non-thinking run:

| Attempt | Mode | Elapsed | Acceptance tests | Result |
|---|---|---:|---:|---|
| `pi-q8-01` | Standard Pi reasoning behavior | 56.04 s | 26/26 | Pass |
| `pi-q8-fast-01` | Standard Pi reasoning behavior | 85.21 s | 26/26 | Pass |
| `pi-q8-nothink-02` | `reasoning_effort="none"` | 48.97 s | **23/26** | Fail |

All three non-thinking failures were monthly-reporting tests:

- `test_acceptance.MonthlyTests.test_accumulates_same_month`
- `test_acceptance.MonthlyTests.test_sorted_and_no_empty_months`
- `test_acceptance.MonthlyTests.test_year_separation`

The code diff isolated the material defect:

```python
# Non-thinking attempt (incorrect year-month grouping):
key = transaction.date.strftime("%m")

# Passing reasoning-enabled attempt:
key = transaction.date.strftime("%Y-%m")
```

The non-thinking attempt grouped all years by month number and returned month-only keys, violating the required reporting behavior. Its other source differences—reordered string equality and `Decimal("0.00")` versus `Decimal("0")`—were not material to the acceptance failures. **Three failing tests corresponded to one remaining conceptual bug, not three independent coding defects.**

**Interpretation:** For this one autonomous repair, reasoning-enabled runs completed correctly and non-thinking did not; non-thinking was 48.97 s versus the fastest successful Q8 run of 56.04 s. A roughly seven-second shorter unsuccessful attempt is not an end-to-end win. More trials are required to estimate reliability.

## 6. Recorded outcome and current recommended configuration

| Setting / workflow | Current recommendation | Why |
|---|---|---|
| Default everyday coding agent | `localcode` | Reasoning-enabled/current behavior passed the 26-test repair benchmark twice under Q8 |
| Quick explanations and low-risk inspections | `localcode-fast` | Very low latency and 0 observed reasoning tokens on short smoke test |
| Ollama attention | Flash Attention automatic | Already observed enabled in logs |
| KV cache | `OLLAMA_KV_CACHE_TYPE=q8_0` | Strong memory and throughput gains on measured workload; benchmark succeeded |
| Context | 16,384 | Better GPU residency than the earlier 32K experiment on this 8GB card |
| High-risk or sensitive repositories | Do not run unsandboxed by default | Everyday Pi has normal user permissions; benchmark safety does not automatically apply |
| Benchmark config | Keep clean `configs/pi-models.json` | Separate experimental settings from reproducible baseline |

The benchmark config was restored with `cp configs/pi-models.original.json configs/pi-models.json` after non-thinking experiments. The systemd Q8 setting was restored and verified by `systemctl show ollama --property=Environment` displaying `OLLAMA_KV_CACHE_TYPE=q8_0`.

## 7. Limitations and validity threats

1. **Small samples:** Two successful Q8 reasoning-enabled coding runs and one genuine non-thinking attempt are insufficient for robust success-rate estimates.
2. **Different task trajectories:** Autonomous tool calls and token counts differ, even with nominally identical instructions. Wall-clock differences cannot be attributed solely to reasoning or KV precision.
3. **Prompt throughput vs task latency:** The direct `/api/generate` benchmark excludes prompt processing, load time, tool execution, and agent overhead; it also stops at 512 tokens.
4. **Token accounting:** “Reasoning tokens = 0” is a reported usage metric from the Pi/OpenAI-compatible path for a short greeting, not a packet capture of every benchmark request. The fast-mode broker was configured to accept `none`, but the attempt's full raw request/response trace was not recorded here.
5. **Correctness coverage:** The 26 acceptance tests cover the seeded Python fixture, not arbitrary coding tasks or security-sensitive software. Passing them demonstrates success **on that fixture**.
6. **Potential cache quality effects:** Q8 changes KV precision; no broad numerical quality or model-output equivalence study has yet been run. One passing benchmark is not proof of absence of quality regressions.
7. **Performance mechanism:** Reduced VRAM use and shifted GPU placement are measured; increased speed may involve reduced offloading, compute kernels, dynamic clocks, or multiple effects. Exact layer placement under both KV settings has not been fully isolated in these runs.
8. **Agent security:** Daily Pi is not wrapped in the benchmark's Bubblewrap sandbox. Cloud quotas are conserved, but file modification/command execution permissions still matter locally.

## 8. Proposed next experiments

**Near-term:**

1. **Freeze the baseline:** Commit this report and record `ollama show --modelfile`, Pi's model config, Ollama service override, software versions, benchmark prompt, fixture hash, and acceptance-test runner version. Avoid storing secrets, tokens, or auth files.
2. **Repeat small A/B trials:** At least several fresh isolated attempts per thinking mode with fixed model settings, rotating run order, collecting outcomes, time, model tokens, and tool calls; keep trusted tests hidden from the agent.
3. **Broaden task coverage:** Add multiple distinct multi-file repairs and feature implementations; evaluate correctness rather than only generation speed.
4. **Consider hybrid workflow:** Non-thinking draft → independent tests → optional reasoning-enabled repair, measuring *total* time and success (not merely first-pass speed).

**Later, and only after compatibility/recovery research:** Evaluate GPU-Unlock or other VRAM-related experiments. Record current GPU state and recovery options before system-level changes. Keep Flash Attention + Q8 as the known-good configuration unless controlled measurements justify a change.

## 9. Reproduction and reference commands

### Current deployment checks (read-only)

```bash
systemctl show ollama --property=Environment
ollama ps
ollama list
sudo journalctl -u ollama -b --no-pager | grep -E 'KV buffer size|llama_kv_cache: size|Flash Attention enabled' | tail -12
```

### Open regular or fast local Pi

```bash
cd ~/Projects/calculator-app
localcode         # regular/current reasoning behavior
# or, in a separate session:
localcode-fast    # reasoning disabled
```

### Read benchmark results without rerunning inference

```bash
cd ~/AI-Lab/benchmarks/coding-tasks/expense-tracker
python3 - <<'PY'
import json
from pathlib import Path
names = ('pi-06', 'pi-q8-01', 'pi-q8-fast-01', 'pi-q8-nothink-02')
for name in names:
    r = json.loads((Path('attempts') / name / 'result.json').read_text())
    a, s = r['agent'], r['score']
    print(f"{name:18} {a['elapsed_seconds']:7.2f}s  {s['passed']:2}/{s['tests_run']}  success={s['successful']}")
PY
```

### Relevant source records

This report was reconstructed from user-provided terminal output and file diffs in the conversation. Canonical machine-readable run records remain under `attempts/<name>/result.json` on the workstation; this report does not replace those records or the benchmark's trusted test suite.
