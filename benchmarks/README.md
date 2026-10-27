# Reproducible benchmark plan

Status: planned, not run. Start with the installed `qwen3:8b` digest recorded in
the root README. This plan needs no package installation. Keep all prompts,
requests, responses, telemetry, and reports beneath this directory.

## Experiment matrix

| Phase | Variable | Fixed controls |
| --- | --- | --- |
| 1: baseline | Qwen3 8B, 2,048 and 4,096 context | Same digest, prompts, decoding, thinking mode, single request at a time |
| 2: context scaling | 8,192 then 16,384; larger only if feasible and within model limit | Same model and output budget; record actual prompt tokens and offload |
| 3: coding models | Approved downloaded candidates, initially 3–8B class | Identical task set, context, output budget and decoding; identify exact quantization and digest |
| 4: quantization | Available quantizations of the same model revision | Same tasks and runtime; separate quality and speed results |
| 5: GPU-Unlock | Baseline A, approved treatment B, restored baseline A | Same hardware, model, requests, context, software and thermal conditions except documented treatment |

Choose specific future model artifacts after reviewing their coding focus,
license, size and available memory. Model installation/download is a separate
approval step because the service storage is outside this workspace. Never
silently substitute a mutable tag for a recorded digest.

## Freeze each experiment

Create `results/<UTC-timestamp>-<experiment>/` and retain:

- A manifest with experiment ID, UTC time, workspace Git revision and dirty
  status, OS/kernel, CPU/RAM, driver, GPU, Ollama CLI/API versions, unit settings,
  free disk/RAM/VRAM, and desktop/background workload notes.
- `/api/tags`, `/api/show` (includes template and parameters), `/api/ps`, and
  `nvidia-smi` snapshots. Capture model metadata before and after to detect tag
  changes. Record model digest, quantization, advertised context and actual
  runtime context/offload. Mark unavailable fields explicitly.
- Exact prompt files and SHA-256 hashes, request JSON, raw streamed responses,
  final timing records, telemetry, errors and scoring notes. Do not commit secrets.
- Explicit settings for `num_ctx`, `num_predict`, `temperature`, `seed`, `top_k`,
  `top_p`, `repeat_penalty`, stop strings, thinking, and keep-alive. Preserve the
  model's chat template; record template differences between models.

Use one client and one request at a time. Observe existing concurrency, KV-cache,
flash-attention and offload settings where available; do not change service
settings to force controls. If defaults cannot be established, label them unknown.
Keep the desktop workload comparable across runs and record idle telemetry.
Do not change GPU clocks, power limits, swap or kernel caches.

## Run protocol

1. Capture inventory and idle telemetry. Confirm adequate free disk and memory.
2. Use a fixed seed (42), temperature 0, top_k 20, top_p 0.95,
   repeat_penalty 1, output cap 512 and explicit context for the initial speed
   suite. Set `think: false` for Qwen3; run thinking-enabled experiments as a
   separate series with a declared token budget. For other models, record whether
   thinking control is supported; never silently accept ignored controls.
3. For every model/context pair, record the first load separately. If already
   loaded, mark it resident; a deliberate unload requires authorization for
   runtime state changes outside the workspace. Model-cold means not resident
   in Ollama, not OS-disk-cache cold. Never drop OS caches.
4. Perform one unscored warm-up, then five measured repetitions per prompt.
   Report warm-up and first-load records separately. Rotate model/context order
   across sessions to reduce temperature and ordering bias.
5. Stream `/api/chat` responses with a monotonic client clock. Record time to
   first nonempty generated token, time to first answer content separately when
   thinking is enabled, and total client wall time. Retain the final API record.
   Set a declared per-request timeout, initially 300 seconds; retain failures.
6. Sample GPU memory/utilization, temperature and power with existing
   `nvidia-smi` at one-second intervals while requests run. Capture host RAM/swap
   and `ollama ps` or `/api/ps` during residence. Sampling gives observed peaks,
   not exact instantaneous maxima. Stop collectors after the run.
7. Record errors, OOM, timeouts, CPU offload, truncation and incomplete answers.
   Stop escalating context after resource failures; do not change system
   settings to make a failing point pass. Verify service health read-only.
8. Summarize median, minimum, maximum and sample count for five repetitions;
   retain every sample. Avoid strong tail-latency claims from five samples.

Inference requests and telemetry collection are future benchmark actions, not
part of the initial read-only inspection. Requests cause transient loading and
may produce service logs outside this workspace; obtain approval before the
first execution under the workspace-only change boundary.

## Metrics and interpretation

Ollama duration fields are recorded in nanoseconds. Calculate rates only when
the corresponding duration is positive and the field exists:

- Prompt processing tokens/s = `prompt_eval_count / (prompt_eval_duration / 1e9)`.
- Generation tokens/s = `eval_count / (eval_duration / 1e9)`.
- Record `load_duration`, `total_duration`, client wall time and streamed latency
  separately. A nonstreamed request cannot measure time to first token.
- Report actual generated token count and `done_reason`; short completions and
  token-cap truncations must be visible. Thinking tokens can distort useful-answer
  throughput; preserve thinking and answer text separately.
- Record GPU memory, RAM, swap, utilization and temperature alongside speed.
  GPU detection alone does not prove full GPU offload.
- Repeated prompts may reuse cached prefixes. Label repeated-prompt results as
  cache-eligible. For prefill comparisons, use a frozen set of distinct prompts
  with differing prefixes and report actual evaluated token counts; do not mix
  these with cached measurements. No claim of cache-free prefill without evidence.
- Tokenizers differ across models: compare latency and task success alongside
  tokens/s, not tokens/s alone.

## Context workload

Separate context allocation from context occupancy. First sweep `num_ctx` using
the same short prompt to measure allocation/offload costs. Then use frozen code
fixtures targeting 25%, 50% and 75% occupancy, reserving room for template and
output. Use actual `prompt_eval_count` to validate occupancy; characters are not
tokens. Freeze calibrated fixtures per tokenizer and retain their hashes.

Place a uniquely identified helper or requirement near the beginning, middle
and end of each code fixture and ask a verifiable question or edit requiring it.
Record correctness at every position. Reject silent truncation as a valid
long-context score. Inspect actual runtime context, evaluated tokens and fixture
coverage; a model's advertised limit is not evidence of GPU feasibility.

## Coding quality suite

Freeze at least 12 small tasks before comparing models: three each for function
implementation, bug fixes, refactoring and test writing. Begin with Python
standard-library tasks to avoid dependencies. Include empty inputs, Unicode,
boundary values and regression cases. Keep prompts, starter code, expected
interfaces and independent tests versioned. Use the same tasks for every model.

Score first-attempt test pass rate, full-task pass rate, interface compliance,
and rubric-based readability (0–2: unusable, needs edits, clear). For test-writing
tasks, assess whether the produced tests catch predefined buggy variants as well
as pass the correct implementation. Record raw outputs and extraction rules.
Use five declared seeds for a separate quality series if sampling is enabled;
do not confuse repeated deterministic speed trials with independent solutions.

Generated code is data until reviewed. Execute only after review, within a
restricted workspace, with a timeout and no network or access to credentials.
If suitable isolation is unavailable, record static/manual evaluation instead.
Do not install an evaluator or sandbox without approval. Report the final
quality/speed/memory tradeoff rather than a single opaque composite score.

## Future GPU-Unlock experiment gate

Before any treatment, identify the exact project/repository, pinned revision,
claimed mechanism, required changes, driver/GPU compatibility, and rollback
procedure. The name alone does not establish its behavior or expected benefit.
Obtain explicit approval for installation, system/driver changes, and activation.
Archive the unchanged baseline first. No GPU-Unlock change is authorized here.

After approval, compare A/B/A with identical artifacts and repeated runs. Include
coding correctness, crashes, memory pressure, GPU offload, power and thermal
behavior alongside throughput. Document every deviation; if rollback does not
restore baseline behavior, treat the comparison as inconclusive. Make no speedup
claim before measurements.
