# AI-Lab: GPU-Unlock, Ollama GPU Residency, and Flash Attention Benchmarks

**Experiment dates:** October 26–27, 2026 (local CDT; some attempt timestamps recorded in UTC)  
**Status:** Completed exploratory study; conclusions are not statistically validated.  
**Platform:** Ubuntu 24.04, Linux `7.0.0-38-generic`, AMD Ryzen 5 5600X, NVIDIA GeForce RTX 3070 Ti (GA104, 8 GB), 32 GB system RAM; NVIDIA `595.99.02-open` driver.  
**Software:** Ollama v0.40.11, Qwen3.5 9B Q4_K_M (`pi-qwen35-9b-16k`), 16,384-token requested context, Pi coding agent v1.4, Python benchmark scripts.  
**Experiment under test:** Zagitta/gpu-unlock v1.1.0, source commit `6081407b312aa3139a2bed62bdda354f4ffddc1d`.

> **Scope:** These are measurements from one PC, one quantized model, and a small number of trials. Improvements in a synthetic kernel benchmark must not be treated as general LLM or coding-agent gains.

## Executive summary

1. GPU-Unlock successfully activated on the RTX 3070 Ti in a *temporary boot* using `gpu_unlock.targets=0000:0b:00.0`. Successful kernel logs included `gpu_unlock: unlocked`; normal boot without this parameter leaves the unlock inactive. The experimental DKMS package and firmware remained installed during these tests, but activation was boot-specific.
2. Synthetic CUDA matrix-multiplication throughput improved approximately **1.86–2.16×** for the measured FP16/BF16/TF32-permitted GEMM tests.
3. The **biggest practical inference optimization was GPU residency**: Ollama's automatic stock fitting once placed 32/33 layers on GPU (60.40 generated tokens/s), while explicit `num_gpu=33` placed 33/33 layers on GPU (82.14 tokens/s). This was a **36.0% throughput gain without GPU-Unlock**.
4. With 33/33 layers on GPU, stock and unlocked token generation measured **82.14 versus 82.67 tokens/s**, respectively (**+0.65%** unlocked), too small to establish a real improvement in this sample.
5. Longer prefill comparisons showed unlocked throughput approximately **+0.67%** at 2,907 input tokens and **+1.17%** at 5,857 tokens (single three-run samples). Small differences may be ordinary measurement variation.
6. Three Expense Tracker agent attempts all passed **26/26** acceptance tests. Elapsed times were **84.38 s** (stock), **64.90 s** (unlocked), and **44.92 s** (stock with explicit `OLLAMA_FLASH_ATTENTION=1`). Different model-turn paths and a **24.78 s first turn** in the original stock attempt confound causality.
7. Crucially, even when `OLLAMA_FLASH_ATTENTION:false` appeared in the server configuration, the Q8-quantized V cache caused the llama.cpp backend to **enable Flash Attention automatically**. The explicit environment change was **not a true OFF-versus-ON attention-kernel comparison**.

## Configuration and implementation

- Main OS and GPU: Ubuntu 24.04 / kernel `7.0.0-38-generic`; NVIDIA RTX 3070 Ti GA104, PCI `0000:0b:00.0`, 8192 MiB installed VRAM.
- Unlock installed using the project's v1.1.0 DKMS and firmware Debian packages. A separate fallback kernel `7.0.0-31-generic` had been boot-tested; the fallback does **not** have a usable NVIDIA driver in this environment. Original kernel/initramfs backups were preserved on the user's machine.
- Activation was tested using temporary GRUB edit: append `gpu_unlock.targets=0000:0b:00.0` to the normal kernel's boot line. The ability to load the module alone does not establish an active unlock.
- Inference model: `pi-qwen35-9b-16k`, Qwen3.5 9B Q4_K_M; `num_ctx=16384`, `OLLAMA_KV_CACHE_TYPE=q8_0`, `think=false`, deterministic generation options (`temperature=0`, `seed=42`) in direct API tests.
- Ollama / llama.cpp output confirmed Q8 KV buffers: **272 MiB** total, **136 MiB K** and **136 MiB V**; 33/33 GPU layers once full GPU allocation was requested.
- For the first stock automatic-offload load, Ollama projected 5,278 MiB on device but rejected it to preserve approximately 1,927 MiB free, choosing **32/33** GPU layers and around **683.55 MiB CPU-mapped model buffer**. Explicit request option `num_gpu=33` successfully achieved 33/33 and a 4,812.25 MiB CUDA model buffer.
- All GPU residency percentages refer to `ollama ps` reporting; they are not claims of a larger physical VRAM capacity.

## A. Synthetic GPU matrix multiplication

Reference scripts and local results: `benchmarks/gpu-unlock/benchmark.py`, `benchmarks/gpu-unlock/results/stock-3070ti.json`, and `.../unlocked-3070ti.json`. Five measurement repetitions of 20 iterations each were used for the reported matrix sizes. Figures are achieved TFLOPS, rounded.

| Operation | Dimension | Stock TFLOPS | Unlocked TFLOPS | Measured factor |
| --- | ---: | ---: | ---: | ---: |
| FP16 | 2048 | 32.97 | 69.89 | 2.12× |
| BF16 | 2048 | 33.90 | 73.33 | 2.16× |
| TF32 permitted | 2048 | 17.75 | 34.22 | 1.93× |
| FP16 | 4096 | 42.04 | 78.38 | 1.86× |
| BF16 | 4096 | 40.40 | 81.24 | 2.01× |
| TF32 permitted | 4096 | 20.71 | 39.80 | 1.92× |

**Qualification:** This is a limited before/after microbenchmark. No replicated cross-boot randomization, temperature/clock normalization, or independent verification of the actual TF32 kernel selection was performed. `TF32 permitted` is deliberately not described as a confirmed TF32-only operation.

## B. Qwen3.5 generation and GPU residency

Direct Ollama benchmark (`benchmarks/gpu-unlock/benchmark_ollama.py`) used a 69-token prompt and measured generation throughput over three runs after warmup. The automatic stock run generated a different number of tokens from the other runs; use tokens/s rather than raw wall time for that initial comparison.

| Boot / setting | GPU layers | Avg generation tok/s | Avg prompt tok/s | Output tokens |
| --- | --- | ---: | ---: | ---: |
| Stock; Ollama auto-fit | 32/33 | 60.40 | 1,014.76 | 343/run |
| Stock; requested `num_gpu=33` | 33/33 | 82.14 | 1,094.62 | 280/run |
| Unlocked; auto-fit | 33/33 | 82.67 | 1,116.03 | 280/run |
| Stock; explicit Flash Attention | 33/33 | 82.71 | 1,147.09 | 280/run |

**Interpretation:** Fixing partial CPU offload yielded a **36.0%** stock generation-throughput improvement (60.40 to 82.14 tok/s). Comparing 100% GPU-resident runs gave only **+0.65%** with GPU-Unlock. The explicit Flash Attention configuration measured **+0.69%** generation throughput over stock full-GPU in this three-run sample; this cannot establish a causal Flash Attention effect because the backend already enabled it with quantized V cache.

## C. Prompt prefill: repeated input lengths

The first prefill implementation exhibited prefix caching: repeated trials falsely appeared to process tens to hundreds of thousands of tokens per second. It was **discarded**. A revised script varied the beginning of prompts and recorded actual input-token counts. The **same script checksum** was verified on stock and unlocked runs. A prior oversized input also hit an observed 8,192-token processing limit and was excluded. The revised experiment used 1,165, 2,907, and 5,857 input tokens.

Median throughput of three runs, tokens/second:

| Input tokens | Stock full-GPU | Unlocked full-GPU | Stock with explicit Flash Attention |
| ---: | ---: | ---: | ---: |
| 1,165 | 2,839.02 | 2,993.60 | 2,718.94 |
| 2,907 | 4,069.31 | 4,096.48 | 3,749.15 |
| 5,857 | 5,299.64 | 5,361.71 | 4,851.37 |

Unlocked versus stock: **+5.44%** at 1,165 tokens (the short workload had substantial run variation), **+0.67%** at 2,907 tokens, and **+1.17%** at 5,857 tokens. Explicit Flash Attention was slower than the previous stock medians at each of these lengths. Small samples, differing system load, and prefill caching behavior prevent strong attribution.

**Important Flash Attention finding:** Logs from the *pre-override* stock Ollama process contained both `OLLAMA_FLASH_ATTENTION:false` and `llama_init_from_model: enabling flash_attn since it is required for quantized V cache`; subsequent log lines showed `llama_context: flash_attn = enabled` and `warmup: flash attention is enabled`. With the explicit systemd override, the same backend status was reported. Thus the controlled contrast was an **environment flag difference, not a confirmed execution-path difference**.

## D. End-to-end Pi autonomous coding benchmark

Benchmark directory: `benchmarks/coding-tasks/expense-tracker/`. The agent ran inside the established `bubblewrap` isolation and Ollama inference broker/bridge, operating on a task-specific `/work` copy. The trusted evaluator ran 26 regression tests. The agent could read, bash, edit, and write within the restricted workspace. Each attempt had its own state.

| Attempt directory | Environment label | Agent elapsed | Turns | Output tokens | Tool calls | Tests |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `gpu-stock-coding-01` | Stock, prior Flash Attention flag unset | 84.38 s | 13 | 4,701 | 14 | 26/26 |
| `gpu-unlock-coding-01` | GPU-Unlock | 64.90 s | 13 | 4,950 | 14 | 26/26 |
| `stock-flash-coding-01` | Stock, explicit `OLLAMA_FLASH_ATTENTION=1` | 44.92 s | 10 | 3,308 | 11 | 26/26 |

The earliest stock and unlocked attempts both reported **13 model turns, 14 tool calls**, and identical final package content under `work/expense_tracker`, but followed different generation paths. Token accounting for stock: input 6,001, output 4,701, cacheRead 63,400, totalTokens 74,102; unlocked: input 5,653, output 4,950, cacheRead 68,928, totalTokens 79,531. These totals combine differently priced operations and must **not** be treated as equivalent GPU work.

### First-turn anomaly

| Attempt | First turn | Sum of turn durations | Sum of recorded tool durations |
| --- | ---: | ---: | ---: |
| Stock | **24.78 s** | 82.95 s | 0.27 s |
| Unlocked | **2.50 s** | 63.49 s | 0.22 s |
| Stock explicit Flash Attention | **2.50 s** | 43.87 s | 0.16 s |

The first stock turn alone exceeded the corresponding unlocked turn by **22.28 s**, which is greater than the entire **19.48 s** wall-time difference between those attempts. If first-turn durations are subtracted *descriptively*, the remaining model-turn durations are **58.17 s** (stock) versus **60.99 s** (unlocked), but these later turns used different token paths and are not a controlled per-token throughput comparison.

The stock Flash Attention attempt finished 39.46 s sooner than the first stock attempt but used **three fewer turns**, **1,393 fewer generated tokens**, and **three fewer tool calls**, while avoiding the slow initial turn. This supports the interpretation that task-path variance and warmup/state are major contributors; it **does not** demonstrate that the Flash Attention flag accelerated the kernel.

### Model-loading timing nuance

The stock Ollama log displayed a loading event at **Oct 26, 22:07:11–22:07:32 CDT**, whereas `gpu-stock-coding-01/result.json` recorded its agent start at **2026-10-27T03:08:33.808346Z** (= **Oct 26, 22:08:33 CDT**). The logged model load finished about one minute before the measured agent start. It therefore **does not establish that model loading caused the first turn's 24.78 s**. Other reasons for that anomaly were not isolated.

## Interpretation and practical recommendations

- **Best demonstrated practical win:** Ensure Qwen3.5 9B uses all 33 GPU layers and keep Q8 KV caching where compatible. Ollama automatic memory fitting can choose CPU offload despite sufficient physical VRAM for a forced full-GPU load; verify actual residency using `ollama ps` and loading logs rather than assuming it.
- **Flash Attention:** The backend was already enabling Flash Attention due to the quantized V cache. Keeping the explicit environment setting is reasonable if stable, but a speed benefit from the flag has **not** been demonstrated.
- **GPU-Unlock:** Large GEMM gains did not translate into meaningful sustained Qwen3.5 inference speedups in these tests. Keep the unlock as an **optional, one-boot experiment**, not a recommended permanent system modification, until benefits and hardware risks are evaluated more thoroughly.
- **Agent benchmarking:** Enforce equivalent startup conditions; warm the model; capture model loads and per-request timings; record number of turns, output tokens, input/cache-read tokens, tool calls, and correctness. A single successful agent attempt is not a stable performance estimate.
- **Operational caution:** GPU-Unlock uses experimental low-level GPU firmware/driver behavior. Preserve normal-boot and recovery routes, and never imply it increases physical VRAM.

## Reproduction references and data hygiene

Relevant repository paths expected in this project:

```text
benchmarks/gpu-unlock/benchmark.py
benchmarks/gpu-unlock/benchmark_ollama.py
benchmarks/gpu-unlock/benchmark_prefill.py
benchmarks/gpu-unlock/results/stock-3070ti.json
benchmarks/gpu-unlock/results/unlocked-3070ti.json
benchmarks/gpu-unlock/results/ollama-stock.json
benchmarks/gpu-unlock/results/ollama-stock-fullgpu.json
benchmarks/gpu-unlock/results/ollama-unlocked.json
benchmarks/gpu-unlock/results/ollama-stock-flash.json
benchmarks/gpu-unlock/results/prefill-stock-v2.json
benchmarks/gpu-unlock/results/prefill-unlocked-v2.json
benchmarks/gpu-unlock/results/prefill-stock-flash.json
benchmarks/coding-tasks/expense-tracker/runner.py
benchmarks/coding-tasks/expense-tracker/security/bridge.py
benchmarks/coding-tasks/expense-tracker/trusted/
```

Agent attempt folders (`attempts/*/`), agent state, generated workspace copies, broker sockets, raw auth/session material, and local runtime directories should remain excluded from the public repository. The aggregate figures above were transcribed from terminal outputs and are not a substitute for an immutable, sanitized experiment archive.

### Suggested follow-up when resuming

1. Check that the current local Pi launcher consistently requests `num_gpu=33` (without relaxing the inference bridge's security controls); compare `ollama ps` and offload logs after normal usage.
2. Build a benchmark harness that warms Ollama once, records inference load/prefill/decode timings separately, and performs several matched ABBA-style trials across stock and unlocked boots.
3. Benchmark additional representative coding tasks; track success rate as well as runtime and generated token counts.
4. Optionally revisit Flash Attention only with a **genuine backend-level on/off comparison**, avoiding settings combinations that automatically force it on.
5. Keep the stock GPU setup with Q8 KV caching as the default until repeated real-world evidence justifies a change.

**Bottom line:** The approximately 2× GPU-Unlock GEMM result is measurable; a sustained Qwen3.5 9B inference acceleration was **not** established. The fastest observed agent attempt was **44.92 s with 26/26 passing tests**, but it was a shorter generation path, not proof of a hardware or Flash Attention advantage.
