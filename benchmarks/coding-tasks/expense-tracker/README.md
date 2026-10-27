# Experiment 3: Mini Expense Tracker coding benchmark

Python 3.12+, standard library only. The dedicated root-owned Bubblewrap helper
and exact-path AppArmor allowance are installed and trusted offline isolation
checks pass. No Pi/Codex agent or inference request has been launched. Actual
agent trials and generated-code execution still require separate approval.

## Layout and trust boundary

| Path | Purpose | Visible to agent |
| --- | --- | --- |
| `fixtures/buggy/` | Frozen starting package, short application README, two smoke tests | Copied into `/work` |
| `fixture-manifest.json` | SHA-256 of every starting file | No |
| `trusted/reference/` | Correct implementation | Never mounted |
| `trusted/regression/` | 26 independent unittest acceptance tests | Only in evaluator, after agent exits |
| `trusted/evaluate.py` | Machine-readable unittest scorer | Only in evaluator |
| `trusted/mutations.json`, `expected-failures.json` | Operator-only defect manifest | Never mounted |
| `trusted/test_runner.py`, `test_bridge.py` | 32 safety/reset/transport tests | No |
| `configs/` | Fresh benchmark-only Pi/Codex configuration templates | Copied into separate agent state |
| `runner.py`, `prompt.txt` | Orchestration and common agent prompt | Prompt only |
| `validation/` | Authored-code validation and isolation-probe logs | Never mounted |
| `attempts/<name>/work/` | A new writable buggy copy for each attempt | Yes, as `/work` |
| `attempts/<name>/agent-state/` | Fresh per-attempt Pi/Codex state | Yes, as `/agent-state` |
| `attempts/<name>/agent/`, `regression/`, `result.json` | Raw logs, timing, exit code, score | No |

Only the application README goes into the project copy. It describes the API and
expected behavior without revealing defect locations or causes. Do not give the
agent this operator README, the reference, or the regression suite.

Four reproducible source mutations cover totals, category matching, inclusive
date bounds, and month/year reporting. The fixture plus hash manifest provides a
stable starting state without changing the workspace Git history. The correct
reference was implemented first; independent tests import whichever package is
being evaluated and never import the reference or inspect its implementation.

## Validate without launching agents

From this directory:

```sh
python3 runner.py validate
python3 -B -m unittest discover -s trusted -p "test_*.py" -v
python3 runner.py validate-isolation
```

`validate` executes only the benchmark author's reference/buggy copies and four
temporary individually repaired variants. It verifies exact expected failures,
two hash-identical resets, and attempts a live hidden-file-read isolation probe.
Never point a host Python process at an agent-edited directory. Run the visible
smoke tests only on the frozen authored fixture, or inside the isolated agent.

Current results: reference **26/26**, buggy **15/26** with exactly 11 intended
failures and zero import errors. All four individual defect checks pass. Two
resets are identical. See `validation/summary.json` and `VALIDATION.md`.

**Current isolation status:** trusted live filesystem, network, permission and
cleanup probes pass using `/usr/local/libexec/ai-lab-expense-bwrap`. The runner
verifies helper/profile ownership, modes and hashes, retains the global userns
restriction, unshares networking in all phases and disables nested userns.
The historical AppArmor failure and approved repair are recorded in VALIDATION.md.
No agent-written package is ever imported directly by a host Python evaluator.
A failure in any live isolation gate stops execution; there is no fallback.

## Reproducible preparation

```sh
python3 runner.py prepare inspection-only
```

This creates a fresh copy and initial manifest, with fresh configuration state;
it launches nothing. Names cannot overwrite earlier attempts. Use a new name to
reset; the runner never reuses edited directories. It checks the frozen manifest
before every copy. Keep the fixture and trusted tree under operator control.

## Future approved Pi attempt

These are prepared commands, **not yet executed**. Run only after separate agent-trial approval and
after live isolation validation passes. Resolve runtime paths on the host using
read-only tools, recording exact agent/model versions and model digests. The
examples use the installed Experiment 2 Pi and Node releases; change a path only
if the installed version differs. No models are installed by this runner.

```sh
NODE_ROOT="$HOME/.nvm/versions/node/v24.22.1"
PI_ROOT="$HOME/.pi/agent/install/releases/1.4.0"
PROMPT="$(cat prompt.txt)"
python3 runner.py run pi-01 --approved --ollama-bridge \
  --runtime "$NODE_ROOT" --runtime "$PI_ROOT" -- \
  "$NODE_ROOT/bin/node" \
  "$PI_ROOT/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js" \
  --offline --no-extensions --no-mcp --no-skills --no-prompt-templates \
  --provider ollama --model pi-qwen35-9b-16k \
  --tools read,bash,edit,write --mode json --no-session "$PROMPT"
```

The runner sets `PI_CODING_AGENT_DIR=/agent-state/pi`. Its fresh models.json
targets the existing 16K alias with a 2,048-token per-response output budget,
temperature 0 and seed 42. Experiment 2 established that thinking remained active
through Pi, so do not claim a matched thinking budget from this configuration.
`--offline` prevents Pi startup network tasks. Model requests would use private
loopback port 11435, a mounted Unix-socket broker and fixed upstream Ollama on
host port 11434. No direct host-network sharing is available.

## Future approved Codex attempt

Use the existing standalone binary, without mounting its host configuration,
sessions, credentials or AppArmor files. Find its actual release directory:

```sh
readlink -f "$HOME/.local/bin/codex"
```

Set `CODEX_ROOT` to the version-specific directory under
`~/.codex/packages/standalone/` that contains that binary (not `~/.codex`).
For example, if the resolved binary is `$CODEX_ROOT/bin/codex`:

```sh
PROMPT="$(cat prompt.txt)"
python3 runner.py run codex-01 --approved --ollama-bridge \
  --runtime "$CODEX_ROOT" -- \
  "$CODEX_ROOT/bin/codex" exec --oss --local-provider ollama \
  --model qwen3:8b-32k --sandbox workspace-write \
  --skip-git-repo-check --ephemeral --json "$PROMPT"
```

The runner supplies a fresh `CODEX_HOME=/agent-state/codex`. Installed Codex
0.164.0 help and the [official CLI reference](https://learn.chatgpt.com/docs/cli/reference)
document the local-provider and exec/sandbox options. No existing Codex settings
are changed. Nested Codex sandbox compatibility is not established: the current policy
intentionally denies nested user namespaces, so its inner sandbox may fail. Preserve and report that failure; do not disable its
sandbox or change security profiles as an automatic workaround. Agent examples
remain untested because agent execution has not been approved.

## Runner behavior and measurements

Each `run` makes a clean attempt, checks isolation twice, launches the supplied
argv without a shell, and records monotonic elapsed time, UTC completion time,
exit code, timeout, stdout and stderr. Wall limit: 600 seconds by default, up to
3,600 via `--timeout`. It evaluates the changed package in a **new** restricted
process even if the agent exits unsuccessfully. The 26 independent tests are
read-only in that process, run with unittest, and produce a JSON score with
passed/failed/error/skipped counts. Evaluation wall limit: 30 seconds; address
space: 512 MiB; CPU and output-file limits also apply. Timeouts retain logs and
changes. A missing score records zero passing with a scoring error. Entire work
trees, including deletions and newly created files, remain available for review;
`initial-manifest.json` enables comparison against the original fixture.

Report score out of 26, runtime, agent exit code, test timeout/errors, changed
files, and manual quality review. Keep raw logs; no pass count can substitute for
review. Both agents should use the same fixture and common prompt. Different
models/contexts/API/thinking controls mean a Pi-versus-Codex comparison does not
isolate the harness alone. Model warm-up/loading and prefix caching must be
recorded separately when actual trials are approved.

## Isolation limits

The sandbox exposes system runtimes read-only, narrow explicitly supplied agent
release directories read-only, the attempt's writable project/state, private
temporary storage and PID/proc/dev namespaces. It hides the rest of the home
directory and workspace. Regression tests and the evaluator are mounted only
in separate trusted probes/evaluation processes, never in the agent sandbox;
the reference is never mounted. There is no host
execution fallback and no option to turn off the evaluator sandbox.

For local Ollama, use `--ollama-bridge`; the removed `--host-network` option is
rejected. An ephemeral Unix broker permits only the three preexisting benchmark
model IDs, text/function-tool inference on `/v1/chat/completions` or
`/v1/responses`, and locally generated discovery/health metadata. It rejects
management, arbitrary URLs, CONNECT, redirects, image/file content and built-in
web/MCP tools. The evaluator never receives the socket. Inference itself has
**not** been tested or authorized by the isolation work; transport tests use a
fake upstream and never connect to Ollama. Unsupported client schemas must fail
closed and be reviewed; do not loosen routing automatically. Discovery metadata
is static and identifies the broker; it is not a fresh inventory of Ollama.

This is a small cooperative coding benchmark, not an adversarial grading system.
Python code running during evaluation can see the tests in that evaluator and
could tamper with its process or fabricate stdout; manually review suspicious
scores. Wall/CPU/address-space limits are not VM-level guarantees or disk quotas.
Protecting against hostile agents, kernel exploits and arbitrary process
exhaustion requires a stronger disposable VM/container with resource quotas.

Only the separately approved helper/profile and benchmark runner/bridge changes
were installed. No existing model/agent configuration, Ollama setting, NVIDIA
driver, system Bubblewrap binary, global namespace setting or GPU-Unlock changed.
See VALIDATION.md for exact policy, results, limits and rollback.
