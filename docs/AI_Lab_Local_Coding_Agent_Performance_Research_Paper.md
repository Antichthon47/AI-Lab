# From Tensor Throughput to Task Completion: An Exploratory Study of Local Coding-Agent Optimization on an 8 GB NVIDIA GPU

**Research manuscript | AI-Lab | 27 October 2026**  
**Study type:** Single-workstation exploratory systems evaluation  
**Status:** Technical research manuscript; not peer reviewed

## Abstract

Deploying an autonomous coding agent on a consumer GPU requires balancing model quality, memory capacity, inference latency, and tool-execution reliability. This study evaluates a locally hosted Qwen3.5 9B model (Q4_K_M) served by Ollama and used by the Pi coding agent on an NVIDIA GeForce RTX 3070 Ti with 8 GB of memory. We examine context size, key–value (KV) cache quantization, reasoning mode, CPU/GPU model-layer placement, an experimental GPU-Unlock kernel module, and Flash Attention configuration. Evidence comprises controlled short-request measurements, synthetic GPU matrix multiplication, long-prompt prefill, and a sandboxed Expense Tracker repair task evaluated against 26 independent tests. Switching from FP16 to Q8_0 KV storage reduced a logged KV allocation from 512 to 272 MiB (−46.9%) and was associated with generation throughput increasing from 36.46 to 59.83 tokens/s (+64.1%) in an early three-run comparison. Explicitly requesting all model layers on the GPU raised stock generation throughput from 60.40 to 82.14 tokens/s (+36.0%) relative to Ollama’s automatic partial-offload configuration. GPU-Unlock increased measured dense matrix-multiplication throughput by approximately 1.86–2.16×, yet produced only a 0.65% difference in fully GPU-resident generation throughput and about 0.67–1.17% on two longer prefill workloads. All three later coding-agent runs passed 26/26 tests, but their completion times ranged from 44.92 to 84.38 seconds because of a first-turn latency anomaly and different agent trajectories. Ollama logs further showed that quantized V-cache requirements enabled Flash Attention even when the explicit environment flag was false. Overall, practical performance depended more clearly on model placement, memory management, and the number of agent turns than on peak synthetic tensor throughput. The conclusions are exploratory and are not causal estimates from replicated trials.

**Keywords:** local large language models; autonomous coding agents; GPU inference; KV-cache quantization; model offloading; Flash Attention; tensor throughput; reproducible benchmarking.

## 1. Introduction

Local large language model (LLM) deployments can provide offline operation, direct control over the software environment, and independence from per-request cloud API charges. Their performance, however, is constrained by memory capacity and by the fact that an autonomous agent repeatedly alternates between language-model inference and external actions. A faster graphics processor or attention kernel does not necessarily shorten task completion if the model spills into system memory, generates unnecessary tokens, or takes a longer sequence of actions.

This paper presents an integrated case study of an experimental Linux coding environment, AI-Lab, assembled around the Pi 1.4.0 coding agent, Ollama 0.40.11, and a Qwen3.5 9B Q4_K_M model. The workstation contains a GeForce RTX 3070 Ti with 8 GB of nominal video memory. The investigation progressed from initial model deployment and agent correctness to KV-cache quantization, reasoning-mode control, model residency, experimental tensor-rate unlocking, and attention configuration. Rather than treating all observed improvements as equivalent, the analysis distinguishes synthetic computational throughput, inference throughput, and end-to-end software-engineering outcomes.

The study asks three research questions:

**RQ1 — Memory and placement.** To what extent do KV-cache format and CPU/GPU layer residency affect throughput and correctness for a 9B-parameter quantized model on an 8 GB GPU?

**RQ2 — Computation versus application performance.** Do increases in dense GPU matrix-multiplication throughput from GPU-Unlock translate into measurable improvements in autoregressive generation, prompt processing, and autonomous coding-task completion?

**RQ3 — Agent-level behavior.** How do reasoning settings, startup state, output-token counts, and tool-use trajectories influence both latency and correctness?

The contribution is a transparent, single-machine evaluation with measured values, trace-based explanations, and explicit threats to validity. It is not a generalized hardware review or a statistically powered comparison of inference engines.

## 2. Technical Background and Related Work

### 2.1 Computation, memory bandwidth, and inference

The Roofline model relates achievable compute throughput to arithmetic intensity and hardware memory bandwidth [1]. Its central implication for this study is that higher peak arithmetic throughput cannot guarantee an equivalent speedup for a workload limited by memory traffic or sequential dependencies. Autoregressive decoding processes output tokens iteratively and may behave differently from large, dense, batched matrix multiplication. This distinction motivates separate measurements of matrix kernels, prompt prefill, token decoding, and complete agent runs. The memory-management challenges of LLM serving have also been documented in work on PagedAttention [3]; that work supplies context but is **not** a component evaluated here.

### 2.2 Flash Attention and KV-cache precision

FlashAttention uses an input/output-aware attention algorithm to limit costly transfers between levels of GPU memory [2]. Ollama provides settings for Flash Attention and KV-cache formats such as FP16 and Q8_0 [4]. KV-cache quantization can substantially reduce memory consumption, although any effect on generated content remains model- and task-dependent. Ollama’s current documentation describes automatic Flash Attention selection on supported backends [4], making configuration flags distinct from the kernels actually executed.

### 2.3 Model and runtime

Qwen3.5 9B is a dense member of the Qwen3.5 family with a hybrid arrangement of recurrent/linear-attention and conventional attention components [5]. This architectural mix is relevant to interpreting attention-specific optimizations; improvements in one class of kernels need not dominate total inference time. The experimental deployment used a quantized Q4_K_M checkpoint through Ollama’s llama.cpp-based runtime, which supports CPU/GPU hybrid inference and quantized execution [6, 7]. The primary experiment concerns text-based coding tasks, not the model’s multimodal performance.

### 2.4 Experimental GPU modification

The third-party GPU-Unlock module seeks to modify low-level tensor instruction throughput on supported NVIDIA Ampere GPUs before the standard NVIDIA driver binds the device [8]. Its stated purpose and implementation motivate the dense GEMM experiments, but the module is not a vendor-supported optimization and does not increase the physical VRAM capacity. This study treats it as an opt-in research intervention with explicit rollback procedures.

## 3. Experimental Environment and Methodology

### 3.1 Hardware and software

**Table 1. Workstation and primary software configuration**

| Component | Observed configuration |
|:--|:--|
| Operating system | Ubuntu 24.04 (separate SSD from Windows); Linux 7.0.0-38-generic during GPU-Unlock study |
| Processor and RAM | AMD Ryzen 5 5600X, 6 cores/12 threads; 32 GB system RAM |
| Graphics processor | NVIDIA GeForce RTX 3070 Ti (GA104), 8 GB nominal VRAM; PCI 0000:0b:00.0 |
| NVIDIA driver | 595.99.02-open during GPU-Unlock study |
| Local inference | Ollama 0.40.11; llama.cpp-based CUDA runner |
| Model | Qwen3.5 9B, Q4_K_M, tag `pi-qwen35-9b-16k` |
| Agent | Pi coding agent 1.4.0; Node.js 24.22.1 |
| Requested context | 16,384 tokens for the main comparisons |
| Experimental GPU modification | Zagitta/gpu-unlock 1.1.0, source commit `6081407b312aa3139a2bed62bdda354f4ffddc1d` |
| Task-level security | Bubblewrap-restricted workspace, AppArmor launcher policy, and narrow Ollama request bridge |

The local command-line workflows use `localcode` for the normal agent and a separate `localcode-fast` configuration for low-reasoning experiments. The everyday launcher has the user’s ordinary filesystem privileges; the *benchmark* agent runs in a separate restricted environment. Bubblewrap exposes mechanisms for constructing such a namespace-based environment but does not by itself confer a fixed security policy [9].

### 3.2 Measurements and analytic conventions

The investigation used four levels of observation: (i) Ollama logs of KV allocation, memory fitting, and layer placement; (ii) direct Ollama generation/prefill rates, based on API-reported token counts and nanosecond durations; (iii) CUDA-event-timed PyTorch matrix multiplication; and (iv) Pi agent task elapsed time and a trusted acceptance suite. For inference, throughput is the relevant token count divided by the corresponding evaluation duration. GEMM rate is represented in achieved TFLOPS. End-to-end runtime is the runner’s measured agent wall time.

For two conditions, the reported *relative throughput gain* is (new rate ÷ baseline rate − 1) × 100%. For end-to-end time, the reported *reduction* is (baseline time − new time) ÷ baseline time × 100%. Three-run arithmetic means are reported for generation; three-run medians for the revised prefill experiment. Synthetic GEMM testing used five repetitions with 20 iterations each for the reported matrix sizes. No confidence intervals are presented: the source record contains too few independent cross-boot replicates to justify a reliable inferential estimate.

### 3.3 Coding-agent task and correctness evaluation

The benchmark asks the agent to repair a seeded Python `expense_tracker` package to satisfy the package README while preserving the public API. The agent can inspect and edit the isolated project and execute its visible unit tests. A trusted evaluator subsequently runs **26 independent acceptance tests**. Attempts have separate workspaces and agent-state directories. The benchmark runner, bridge, and evaluator were developed with additional security/infrastructure checks (32 passed in the recorded mock-upstream infrastructure trial).

A passing score of 26/26 means that the generated package satisfied this fixture’s acceptance tests. It does not establish general software correctness, and tests themselves do not measure resistance to security vulnerabilities. Inference bridge permissions were constrained; a first attempt to add `reasoning_effort` was rejected until the broker explicitly allowed the value `none`.

### 3.4 Configuration and comparison phases

Early experiments contrasted FP16 and Q8_0 KV-cache settings, and standard versus non-thinking reasoning. Later tests compared the stock GPU with GPU-Unlock, while separately controlling the number of model layers on the GPU. The GPU-Unlock module was activated only for a selected temporary GRUB boot via `gpu_unlock.targets=0000:0b:00.0` and verified by the kernel log message `gpu_unlock: unlocked`. A normal boot omitted this parameter. Distinct GPU-memory states and automatic layer-fitting decisions in the first runs required follow-up tests with `num_gpu=33` to establish a comparable full-GPU placement.

The experiment also explicitly enabled `OLLAMA_FLASH_ATTENTION=1` after observing its earlier default environment value as false. However, backend logs showed the Flash Attention algorithm already active before this change. The last phase is therefore labeled an **explicit environment-setting comparison**, not a genuine attention-kernel OFF/ON comparison.

## 4. Results

### 4.1 Initial deployment and context-window trade-off

Initial 16K and 32K coding-agent trials showed that increasing context requirements could reduce the number of model layers placed on the GPU. One earlier repository-inspection measurement on Qwen3.5 9B reported **35.06 seconds** median and approximately **34.4 generated tokens/s** at 16K with roughly 30/33 layers on GPU, while a distinct 32K trial reported **73.31 seconds**, **18.88 tokens/s**, and 26/33 layers. These trials should not be interpreted as a controlled context-length comparison because their specific work differed. They nevertheless motivated selecting a 16,384-token operating context for subsequent controlled inference tests.

An initial reasoning-enabled Expense Tracker attempt, `pi-06`, passed all 26 tests in **104.74 seconds**. The validated environment used an explicit Ollama model identifier, a functional agent command, and a sufficiently long inference-bridge timeout. This provided a task-correctness baseline before optimizing memory use.

### 4.2 KV-cache precision: allocation and measured decoding

With a 16,384-token context, logs recorded **512 MiB** of FP16 KV storage (256 MiB K and 256 MiB V). After setting `OLLAMA_KV_CACHE_TYPE=q8_0`, the same context reported **272 MiB** (136 MiB K and 136 MiB V), a **240 MiB or 46.9% reduction**. Ollama’s processor-placement display shifted from approximately 84% GPU under FP16 to 88% GPU under Q8; these percentages are placement summaries, not physical GPU capacity changes.

**Table 2. Fixed-prompt generation comparison under FP16 and Q8_0 KV caches**

| Run | FP16 KV (tokens/s) | Q8_0 KV (tokens/s) |
|--:|--:|--:|
| 1 | 36.32 | 58.28 |
| 2 | 36.22 | 60.59 |
| 3 | 36.85 | 60.62 |
| **Mean** | **36.46** | **59.83** |

The fixed direct-API task requested 512 output tokens, used `temperature=0` and `seed=42`, and reported evaluation duration separately from loading and prefill. Q8_0 was associated with a **64.1% improvement** in generation throughput in this early comparison. Because placement also changed and there was no independent multi-boot replication, this is an observed *configuration-level* gain, not an isolated KV arithmetic effect. Two subsequent standard-reasoning Q8 coding attempts passed 26/26 tests in **56.04** and **85.21 seconds**, demonstrating task functionality but also considerable end-to-end variance.

### 4.3 Reasoning control: latency–correctness trade-off

Turning reasoning off reduced latency on simple prompts. In a recorded native Ollama test, a greeting with thinking enabled reached the 2,048-token output limit in 38.91 seconds without a final answer, whereas `think=false` produced a concise reply in 0.38 seconds. A Python primality-function test reduced elapsed time from 32.12 to 2.99 seconds while both generated functions passed **19/19** independently exercised cases. The OpenAI-compatible endpoint also accepted `reasoning_effort="none"` and produced a short successful greeting in 0.27 seconds versus a higher-reasoning invocation that exhausted 512 tokens over 8.94 seconds.

On the multi-step Expense Tracker task, however, the genuine non-thinking attempt `pi-q8-nothink-02` passed **23/26 tests** in **48.97 seconds**, whereas the standard-reasoning `pi-q8-01` run passed **26/26** in **56.04 seconds**. The three failing cases arose from a single defect in monthly aggregation: using month-only grouping (`%m`) instead of year–month grouping (`%Y-%m`). The earlier attempt `pi-q8-nothink-01`, which failed authorization in 0.92 seconds and left 15/26 tests passing, was an infrastructure failure and is *not* included as a model-quality result. The attempt called `pi-q8-fast-01` actually used the ordinary benchmark model configuration, despite its name.

These observations demonstrate that reduced reasoning can help with simple requests, but the one faster *unsuccessful* autonomous attempt does not count as a successful task-level speedup.

### 4.4 Synthetic GPU tensor performance

After successful one-boot activation of GPU-Unlock on GA104, a PyTorch benchmark measured dense GEMM throughput using CUDA events. Table 3 reproduces the recorded achieved TFLOPS figures.

**Table 3. Dense matrix-multiplication throughput before and after GPU-Unlock**

| Input precision / mode | Square dimension | Stock (TFLOPS) | GPU-Unlock (TFLOPS) | Ratio |
|:--|--:|--:|--:|--:|
| FP16 | 2,048 | 32.97 | 69.89 | 2.12× |
| BF16 | 2,048 | 33.90 | 73.33 | 2.16× |
| TF32 permitted | 2,048 | 17.75 | 34.22 | 1.93× |
| FP16 | 4,096 | 42.04 | 78.38 | 1.86× |
| BF16 | 4,096 | 40.40 | 81.24 | 2.01× |
| TF32 permitted | 4,096 | 20.71 | 39.80 | 1.92× |

The approximate **1.86–2.16×** gain is substantial for the tested kernels. However, TF32 was *permitted* rather than the selected kernel being independently verified, and device clocks, temperature, power draw, and controlled A/B boot order were not recorded in a way that permits strong attribution beyond the observed before/after condition.

### 4.5 GPU residency dominates the original Ollama decode contrast

The initial stock inference run used automatic Ollama memory fitting and placed **32 of 33 reported model layers** on the GPU. Its log recorded a target to preserve approximately 1,927 MiB of free GPU memory, with a resulting CPU-mapped model buffer around 683.55 MiB. When the same stock system explicitly requested `num_gpu=33`, it successfully placed **33/33 layers** on the GPU; this was confirmed by both the loading logs and `ollama ps`. The CUDA model buffer was reported at approximately 4,812.25 MiB. Thus GPU-Unlock was **not necessary** to fit the full model on this hardware.

**Table 4. Direct Ollama generation throughput and placement**

| Configuration | Reported GPU layers | Mean decode (tokens/s) | Mean short-prompt prefill (tokens/s) | Output per run |
|:--|:--:|--:|--:|--:|
| Stock, automatic placement | 32/33 | 60.40 | 1,014.76 | 343 tokens |
| Stock, explicit `num_gpu=33` | 33/33 | 82.14 | 1,094.62 | 280 tokens |
| GPU-Unlock, automatic placement | 33/33 | 82.67 | 1,116.03 | 280 tokens |
| Stock, explicit Flash Attention flag | 33/33 | 82.71 | 1,147.09 | 280 tokens |

The change from **60.40 to 82.14 tokens/s** represents a **36.0% increase without GPU-Unlock**, coincident with elimination of one CPU-offloaded layer. Among fully GPU-resident conditions, the GPU-Unlock rate of **82.67 tokens/s** exceeded stock by only **0.65%**. The differences are too small to establish a reproducible GPU-Unlock advantage at three runs per condition. The automatic-stock case generated a different answer length, so its raw wall time was not treated as a matched-request comparison.

### 4.6 Longer-prompt prefill

The first prefill benchmark was invalidated by repeated-prefix caching: subsequent trials reported artificial throughput above 50,000–170,000 tokens/s. A revised script introduced distinct prefixes, and its SHA-256 checksum was verified unchanged across stock and unlocked boots. An earlier input hitting an 8,192-token processing count was excluded rather than asserted to have been evaluated completely. The revised prompts contained 1,165, 2,907, and 5,857 reported input tokens.

**Table 5. Median prefill throughput, three runs per condition (tokens/s)**

| Input tokens | Stock full GPU | GPU-Unlock full GPU | Stock, explicit Flash flag | GPU-Unlock versus stock |
|--:|--:|--:|--:|--:|
| 1,165 | 2,839.02 | 2,993.60 | 2,718.94 | +5.44% |
| 2,907 | 4,069.31 | 4,096.48 | 3,749.15 | +0.67% |
| 5,857 | 5,299.64 | 5,361.71 | 4,851.37 | +1.17% |

The short input displayed greater variation than the medium and long workloads. At 2,907 and 5,857 tokens, the unlocked medians were only about 1% higher. The explicit Flash-flag run produced *lower* median prefill rates than the earlier stock run; these small, nonrandomized samples do not identify the mechanism.

### 4.7 Flash Attention setting versus executed backend

Before adding the explicit environment override, Ollama’s startup configuration printed `OLLAMA_FLASH_ATTENTION:false`. Yet the model-loading sequence also printed `enabling flash_attn since it is required for quantized V cache`, `flash_attn = enabled`, and `warmup: flash attention is enabled`. After setting `OLLAMA_FLASH_ATTENTION=1`, the same backend-active status appeared alongside the true environment value.

Consequently, the observed comparison does **not** identify an effect of turning Flash Attention off and back on. The presence of Flash Attention in the backend before and after the systemd change is a direct log observation, and is consistent with Ollama’s documented automatic enablement on supported configurations [4]. The later generation mean of 82.71 tokens/s versus 82.14 stock (+0.69%) offers no convincing incremental benefit attributable to the explicit flag.

### 4.8 End-to-end autonomous coding and trace decomposition

**Table 6. Selected Expense Tracker coding-agent attempts**

| Attempt | GPU / setting | Elapsed (s) | Model turns | Output tokens | Tool calls | Tests passed |
|:--|:--|--:|--:|--:|--:|--:|
| `gpu-stock-coding-01` | Stock, auto backend attention | 84.38 | 13 | 4,701 | 14 | 26/26 |
| `gpu-unlock-coding-01` | GPU-Unlock | 64.90 | 13 | 4,950 | 14 | 26/26 |
| `stock-flash-coding-01` | Stock, explicit Flash flag | 44.92 | 10 | 3,308 | 11 | 26/26 |

The raw difference between the first two attempts is **19.48 seconds** (a **23.1% lower** elapsed time in the unlocked run). Inspection of the Pi JSON trace showed that the first model turn took **24.78 seconds** for stock but only **2.50 seconds** for GPU-Unlock: a **22.28-second difference**, larger than the entire end-to-end gap. The sum of recorded model-turn durations was **82.95 seconds** for stock and **63.49 seconds** for unlock; tool execution accounted for only **0.27** and **0.22 seconds**, respectively. Subtracting the anomalous first turn *descriptively* leaves **58.17 seconds** of stock model-turn time versus **60.99 seconds** unlocked. Later turns differed in content and length, so this subtraction is not a controlled throughput comparison.

The third attempt, with the explicit Flash Attention environment setting, completed in **44.92 seconds** with 26/26 tests, but used only **10 model turns, 3,308 generated tokens, and 11 tool calls**. Its first turn lasted **2.50 seconds**. The previous stock attempt used 13 turns and 4,701 generated tokens. A shorter agent path and absence of the earlier startup anomaly can explain much of the time reduction without requiring a Flash Attention speedup. Both initial stock and unlocked attempts generated identical final files under `work/expense_tracker`, but their intermediate actions and output-token distributions differed.

Finally, the available stock Ollama logs recorded model loading at approximately **22:07:11–22:07:32 CDT** and the benchmark’s agent start at **22:08:33 CDT**. This shows that the *logged* model-load event ended before the measured run began. Model loading therefore cannot be established as the cause of the unusually slow 24.78-second first turn from the available evidence.

## 5. Discussion

### 5.1 Why synthetic GPU gains did not translate directly to LLM speed

The GPU-Unlock experiment increased achieved dense GEMM throughput by up to approximately 2.16×, while the full-GPU Qwen3.5 decoding comparison remained near 82 tokens/s under both stock and unlocked operation. This is compatible with the general distinction between peak compute and operational intensity highlighted by Roofline analysis [1], and with the mix of kernels and attention mechanisms used in the Qwen3.5 family [5]. The present measurements do **not**, however, include kernel-level profiling sufficient to identify a particular bottleneck or quantify memory-bandwidth saturation. “Likely memory- or kernel-mix-sensitive” is thus an interpretation, not a demonstrated hardware diagnosis.

### 5.2 Model residency as a deployment variable

A seemingly minor automatic memory-fitting choice moved one of 33 reported layers out of GPU residency and coincided with a 36.0% reduction in generation rate relative to explicit full offloading. This effect is much larger than the observed sub-2% GPU-Unlock differences on comparable fully GPU-resident workloads. VRAM accounting and runtime buffer reservations can lead to different placement decisions despite identical physical memory capacity. As a result, benchmark papers and operational dashboards should report actual offload layer counts, model-buffer allocations, cache format, and free-memory targets—not only nominal GPU capacity or whether a model launches.

### 5.3 Correctness-aware optimization of agent workflows

For the Expense Tracker fixture, ordinary reasoning yielded complete acceptance-test success in several attempts, whereas one genuine non-thinking run was faster but incomplete because of a year–month aggregation error. Meanwhile, three later correctly solved attempts varied from 44.92 to 84.38 seconds because they used different output lengths and execution paths. These results support evaluating *time to correct completion*, not token rate alone. They do not justify broad claims that reasoning-enabled models are universally more reliable or that reasoning-disabled modes should be rejected for simple coding work.

### 5.4 Reproducibility and operational risk

GPU-Unlock changed low-level device behavior and required boot-time intervention, with pre-existing initramfs backups and a separately boot-tested fallback Linux kernel. The fallback kernel was not equipped with a compatible usable NVIDIA driver in this machine. The safest operational conclusion is to retain the normal boot path and apply the unlock only for explicit experiments. The study offers no claim about hardware longevity, safety across other cards, or driver compatibility beyond this one system.

## 6. Threats to Validity

**Internal validity.** Several comparisons were sequential rather than randomized. Warmup, GPU clocks, temperature, other GPU processes, prompt caching, dynamic memory fitting, and model reload behavior were not fully controlled. The earlier FP16-versus-Q8 comparison changed both cache storage and GPU residency. A first-turn latency anomaly heavily influenced one coding result, and its cause was not identified. The explicit Flash Attention flag did not create a confirmed kernel-level ON/OFF contrast.

**Construct validity.** CUDA GEMM TFLOPS, Ollama decode tokens/s, prefill tokens/s, and coding-agent wall time measure different quantities. Reported `cacheRead` token counts and output tokens do not imply equal amounts of GPU work. Model-turn timing includes request processing beyond pure CUDA execution. TF32 selection was allowed rather than proven. Passing 26 tests measures success on one seeded fixture, not broad code quality.

**External validity.** Results come from one GPU, one host, one quantized model, a single requested 16K context in the main comparisons, and limited workloads. Pi task paths varied between attempts. No cross-device, cross-model, long-duration stress, or power/thermal study was performed.

**Statistical conclusion validity.** Most inference contrasts comprise only three measurements per condition; later coding comparisons comprise one attempt per configuration. No randomized block design, multi-boot repeats, distributional uncertainty estimates, or hypothesis tests were possible from the available records. Accordingly, small observed differences should not be interpreted as statistically significant speedups.

**Data availability and security.** The public repository includes research documentation and may include sanitized scripts or aggregate JSON; the live machine’s private attempt directories and state should not be assumed published. Raw agent sessions, credentials, broker sockets, and generated workspaces were deliberately excluded from public source control. Reproduction therefore requires a fresh benchmark run and inspection of locally retained source artifacts.

## 7. Conclusions

This exploratory case study illustrates a hierarchy of optimization effects in an 8 GB local LLM deployment. KV-cache quantization materially reduced memory allocation and was associated with higher generation throughput in an early configuration-level comparison. Explicit full-GPU offloading produced the most clearly actionable decode-rate improvement in the later matched-model tests, increasing stock throughput from 60.40 to 82.14 tokens/s. GPU-Unlock produced substantial synthetic FP16/BF16 matrix-performance gains but no demonstrated meaningful sustained improvement in quantized Qwen3.5 generation or longer-prompt prefill. Explicitly enabling Flash Attention did not yield an interpretable OFF/ON contrast because the backend had already enabled the algorithm for quantized V-cache operation.

For autonomous coding, the fastest observed completion was **44.92 seconds with 26/26 tests passing**, but agent trajectories, token budgets, and first-turn state explained much of the variation. The evidence therefore favors optimizing actual GPU residency, context and KV memory, predictable model warmup, and correctness-aware agent workflows before undertaking low-level GPU modifications. More rigorous replicated experiments are required to establish the contribution of any single intervention to real coding-task performance.

## 8. Future Work

A follow-up study should freeze a reproducible model and runtime baseline, then conduct multiple warm and cold attempts per configuration in counterbalanced order across reboots. The runner should collect Ollama load, prefill, and decode durations **per request**, together with requested options, actual GPU offload layers, thermal/clocks telemetry, generated token counts, tool calls, and acceptance scores. It should also expand beyond a single Python repair to distinct bug-fix, multi-file implementation, repository-understanding, and test-writing tasks, reporting both accuracy and time to a correct solution. Reasoning-mode comparisons should include replicated success rates and a staged “fast attempt → tests → standard-reasoning repair” workflow. Future Flash Attention tests require a verified backend kernel-level contrast rather than reliance on an environment variable alone.

## Data and Code Availability

Project repository: **AI-Lab**, `https://github.com/Antichthon47/AI-Lab` (the researcher’s local Git status reported the prior documentation commit `5687d78` on `master`). Key project paths include `benchmarks/gpu-unlock/benchmark.py`, `benchmark_ollama.py`, `benchmark_prefill.py`, `benchmarks/gpu-unlock/results/`, and `benchmarks/coding-tasks/expense-tracker/` with `runner.py`, `security/bridge.py`, and `trusted/`. At the time of the recorded Git status, several newer GPU benchmark scripts and result files remained **untracked**. Their presence on the remote repository should therefore be verified independently. Raw attempt logs and agent state are intentionally local. Aggregated values in this manuscript were consolidated from investigator-supplied terminal output and two earlier AI-Lab findings reports [10].

## Acknowledgments and Disclosure

The measurements and agent implementation were carried out as part of the AI-Lab local coding-agent project. The paper was consolidated from investigator-provided benchmark records with writing assistance from ChatGPT. External tools and projects cited below were not involved in, and do not endorse, the reported experimental conclusions. No external funding or peer-review status has been claimed.

## References

[1] S. Williams, A. Waterman, and D. A. Patterson, “Roofline: An Insightful Visual Performance Model for Multicore Architectures,” *Communications of the ACM*, vol. 52, no. 4, pp. 65–76, 2009. doi: **10.1145/1498765.1498785**. https://doi.org/10.1145/1498765.1498785

[2] T. Dao, D. Y. Fu, S. Ermon, A. Rudra, and C. Ré, “FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness,” *Advances in Neural Information Processing Systems*, vol. 35, 2022. https://proceedings.neurips.cc/paper/2022/hash/67d57c32e20fd0a7a302cb81d36e40d5-Abstract-Conference.html

[3] W. Kwon et al., “Efficient Memory Management for Large Language Model Serving with PagedAttention,” *Proceedings of the 29th Symposium on Operating Systems Principles*, pp. 611–626, 2023. doi: **10.1145/3600006.3613165**. https://doi.org/10.1145/3600006.3613165

[4] Ollama, “Frequently Asked Questions: Flash Attention and K/V Cache Quantization,” software documentation, accessed October 2026. https://github.com/ollama/ollama/blob/main/docs/faq.mdx

[5] Qwen Team, “Qwen3.5-9B Model Card,” Hugging Face, 2026, accessed October 2026. https://huggingface.co/Qwen/Qwen3.5-9B

[6] ggml-org, “llama.cpp: LLM Inference in C/C++,” project documentation, accessed October 2026. https://github.com/ggml-org/llama.cpp

[7] Ollama, “API Reference: Generate Endpoint and Runtime Options,” software documentation, accessed October 2026. https://github.com/ollama/ollama/blob/main/docs/api.md

[8] Zagitta, “gpu-unlock,” open-source kernel-module project; experimental version 1.1.0, source revision `6081407b312aa3139a2bed62bdda354f4ffddc1d` used in this study. https://github.com/Zagitta/gpu-unlock

[9] Containers Project, “Bubblewrap,” README and security model, accessed October 2026. https://github.com/containers/bubblewrap

[10] AI-Lab Research Project, “Local Coding Agent—Experimental Findings” and “GPU-Unlock, Ollama GPU Residency, and Flash Attention Benchmarks,” internal technical reports and investigator-provided execution logs, October 26–27, 2026; associated repository: https://github.com/Antichthon47/AI-Lab

---

**Editorial note.** This manuscript is a research-style synthesis of a small exploratory engineering dataset. It does not claim independent reproduction, statistical significance, or peer review. Quoted environment outputs and trial statistics originate from the project’s recorded terminal logs and internal summaries; external references provide technical background rather than independent validation of the benchmark results.
