# Benchmark validation and isolation

Current status: **the separately reviewed helper/profile are installed; trusted
live offline isolation checks pass. No agents or model inference requests ran.**
See “Approved implementation and validation” below for the latest results. The
original preparation and investigation records are preserved as historical evidence.

## Original preparation record (historical)

Validated 2026-10-26 with the existing Python 3.12 standard library. No AI agents,
agent-written repairs, model requests, downloads or full benchmark attempts ran.

| Check | Result |
| --- | --- |
| Correct reference, independent acceptance suite | 26/26 pass, no errors |
| Four-bug fixture, independent acceptance suite | 15/26 pass, exactly 11 expected failures, no errors |
| Correct reference, visible smoke suite | 2/2 pass |
| Buggy fixture, visible smoke suite | 2/2 pass |
| Repair each of four mutations separately | Exactly its own failing test family disappears |
| Two fresh resets | Identical SHA-256 manifests for all three project files |
| Runner safety tests | 8/8 pass |
| Live hidden-file inaccessibility | **Blocked: Bubblewrap namespace initialization fails** |
| Existing models/configurations/system security | Unchanged by this work |

The four defect families are independently exercised: 3 total checks, 2 category
checks, 3 date-boundary checks, 3 monthly checks. Remaining tests cover validation,
atomic additions, IDs, immutable records, copying, removal, unknown categories,
empty ranges, reversed bounds, and other documented behavior. No regression test
imports or derives expected output from the reference implementation.

`validation/summary.json` records machine-readable results. `reference/`, `buggy/`
and `repair-0/` through `repair-3/` contain the independent suite logs and process
timings. `runner-tests.log` covers reset reproducibility, corrupted-fixture
rejection, mount separation, no network in evaluation, rejection of broad runtime
mounts, explicit approval enforcement, and failure of the isolation probe blocking
agent launch. The smoke-suite logs are recorded separately.

The trusted-only live probe failed with:

```text
bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted
```

This occurred before the probe's Python code ran. Thus a live claim that an agent
cannot read hidden files is not established. Both hidden tests and reference are
outside `attempts/<name>/work`; static mount checks exclude them from the agent
view. The runner nevertheless requires successful live read-denial probes on
every actual run and refuses to execute an agent or generated code if either
fails. `--approved` does not bypass isolation. No security workaround was tried.

A working restricted environment and explicit user approval remain prerequisites
to actual Pi/Codex trials. Agent commands and isolated generated-code evaluation
are prepared but deliberately untested here. The known isolation failure is not
a coding-task failure and should never be scored as agent performance.

## Bubblewrap / AppArmor investigation — 2026-10-26

**Confirmed cause:** the directly launched `/usr/bin/bwrap` enters Ubuntu's
fallback `unprivileged_userns` AppArmor profile. That profile denies capabilities
needed to initialize the sandbox, including `net_admin` for private loopback
configuration. The failure occurs before Python runs the hidden-read checks.
This is separate from the earlier, successfully tested Codex-specific attachment.

This investigation read existing files, installed code/manuals and kernel logs,
and reproduced only a trusted probe in an empty temporary directory. Only this
document is updated. No profiles, packages, runner code, agent configurations,
system settings or models were changed; no agents or generated code ran.

### Invocation and exact denial evidence

`runner.py:sandbox()` resolves `bwrap` through PATH, currently `/usr/bin/bwrap`.
`capture()` uses argv directly, without a shell or AppArmor profile selection:

```text
Python runner (unconfined)
  -> /usr/bin/bwrap --die-with-parent --new-session --unshare-all ...
     -> user namespace creation transitions to unprivileged_userns
        -> namespace-setup capabilities denied
```

The probe binds only the selected project as writable `/work`, exposes system
runtime files read-only, creates private proc/dev/tmp and an empty home, clears
the environment, and attempts reads of the hidden reference/tests and host Codex
configuration. Neither `/tests` nor `/evaluate.py` is mounted in the agent probe.
Evaluation exposes those two paths read-only only after the agent exits, in a
different sandbox. The reference is never mounted. These mount boundaries are
appropriate in principle, but have not yet been exercised successfully here.

The saved `validation/isolation/execution.json` completed at
**2026-10-26 22:58:06.646910 UTC** (17:58:06 CDT), exit 1 after 0.00354 seconds.
Kernel events at that exact time identify:

```text
17:58:06.643 audit 722: operation="userns_create" profile="unconfined"
  pid=30646 comm="bwrap" target="unprivileged_userns" execpath="/usr/bin/bwrap"
17:58:06.644 audit 723: apparmor="DENIED" operation="capable"
  profile="unprivileged_userns" pid=30647 comm="bwrap" capname="setpcap"
17:58:06.644 audit 724: apparmor="DENIED" operation="capable"
  profile="unprivileged_userns" pid=30647 comm="bwrap" capname="net_admin"
```

A fresh read-only diagnosis at **23:01:02.418167 UTC** (18:01:02 CDT) called
the same `sandbox()` builder with an empty temporary work directory and a trusted
`python3 -I -c` print command. It returned exit 1, empty stdout and the identical
loopback error. Audit events **736–739** show `/usr/bin/bwrap` PID 31261
transitioning from `unconfined`; child PID 31262 is denied `setpcap` and
`net_admin` under `unprivileged_userns`. The temporary directory was removed.

Reproduce the historical log query read-only:

```sh
journalctl -k --since '2026-10-26 17:58:06' \
  --until '2026-10-26 17:58:08' --no-pager -o short-iso
```

This is **not** an outright rejection of namespace creation: the `userns_create`
event is an AUDIT transition, followed by capability DENIED events inside the
fallback profile. `/etc/apparmor.d/unprivileged_userns` contains
`audit deny capability,`, allows `userns`, and stacks the fallback onto children.
The `net_admin` rejection is consistent with the failed RTM_NEWADDR loopback
request. Additional `setpcap` denials show setup is affected beyond networking;
removing network isolation would not be an acceptable repair.

Observed host state:

| Item | Observation |
| --- | --- |
| Inspection Python label | `unconfined` |
| `kernel.apparmor_restrict_unprivileged_userns` | `1` |
| `kernel.unprivileged_userns_clone` | `1` |
| `user.max_user_namespaces` | `116327` |
| Bubblewrap | `0.9.0-1ubuntu0.3`, root-owned `/usr/bin/bwrap`, mode 0755, no setuid bit |
| AppArmor package | `4.0.1really4.0.1-0ubuntu0.24.04.9` |
| Profile files inspected | No bwrap/benchmark executable attachment found in `/etc/apparmor.d` |
| Loaded-profile inventory | `/sys/kernel/security/apparmor/profiles` is permission denied; not independently inventoried |

The audit events establish the effective profile for these failing processes
despite the unreadable complete inventory. Unrelated Firefox denials were not
used as evidence for this failure.

### Why the earlier Codex fix does not cover this process

The existing `/etc/apparmor.d/codex-local` attaches to exactly:

```text
/home/binamra/.codex/packages/standalone/releases/0.164.0-x86_64-unknown-linux-musl/bin/codex
```

It uses `flags=(unconfined)` with `userns,`. Earlier records in
`../../local-agent-debug.md` and
`../../results/2026-10-26-codex-apparmor/verification.json` show a tested Codex
child inheriting `codex-local (unconfined)`, with filesystem/network restrictions
still supplied by Codex's sandbox. Those records do not grant the same label to
an independent host Python runner. Today's direct bwrap audit labels prove that
this path is outside that allowance. Do not reuse or broaden the Codex attachment.

### Pi needs an external boundary around the entire process

Installed Pi 1.4.0 source confirms that `dist/core/tools/bash.js` launches the
configured shell with Node `spawn`, the selected cwd/environment, and detached
process groups on Linux. Its `read.js` uses `fs/promises.readFile` directly
inside Node. A cwd and a tool allowlist are not filesystem confinement; wrapping
only the bash tool would leave read/write/edit operations outside the boundary.
Detached shells retain their namespaces, but timeout cleanup must be checked
with descendant processes, not assumed from process-group killing alone.

Run the entire Pi Node process and descendants within the outer sandbox. Keep
extensions/MCP/skills disabled, a disposable HOME and Pi state, minimal runtime
mounts, and no host credentials or hidden files. Pi's project-trust decisions and
`--offline` do not confine its tools or model-request network access. An extra Pi
plugin is unnecessary for this benchmark when whole-process isolation works.
The [official Pi security guidance](https://pi.dev/docs/latest/security) describes
the same permissions and recommends OS/virtualization boundaries.

### Proposed least-invasive repair (not implemented)

1. **Create one dedicated, root-owned benchmark Bubblewrap entry point**, for
   example `/usr/local/libexec/ai-lab-expense-bwrap`, using a verified copy of the
   already installed `/usr/bin/bwrap`. Use a regular executable, not a symlink
   that resolves back to the shared binary; restrict invocation to the benchmark
   operator using appropriate group/mode permissions. Record its source hash and
   refresh this copy deliberately when the distro Bubblewrap receives updates.
   A fixed compiled launcher with vetted arguments would give tighter control
   but adds maintenance; a named opt-in profile invoked through `aa-exec` avoids
   the copy but needs careful transition/access review. Prefer the dedicated
   exact-path entry point for the first targeted test.
2. **Add one exact-path AppArmor namespace allowance** for that executable only.
   Proposed `/etc/apparmor.d/ai-lab-expense-bwrap` contents for administrator
   review, not a loaded or validated policy:

   ```text
   abi <abi/4.0>,
   include <tunables/global>

   profile ai-lab-expense-bwrap /usr/local/libexec/ai-lab-expense-bwrap flags=(unconfined) {
     userns,
   }
   ```

   This follows the mechanism used successfully for this host's Codex. It is
   an explicit namespace exception, **not** an enforcing AppArmor filesystem
   sandbox. It should avoid the fallback capability-denying transition; actual
   inheritance and behavior must be verified after approval. It permits the
   program to set up namespaces, not host root privileges. It still expands
   namespace access for that opt-in application and inheriting descendants;
   application-specific does not mean risk-free.
3. **Change only this runner's Bubblewrap executable selection** to the absolute
   approved helper path. Require correct ownership/hash/path and fail closed if
   absent; remove PATH dependence and never fall back to unsandboxed execution.
   Preserve all mount, PID, environment and network isolation options. Do not
   attach allowances to `/usr/bin/python3`, Node, or shared `/usr/bin/bwrap`.
4. **Limit post-setup namespace use where compatible.** The installed bwrap
   supports `--disable-userns` and `--assert-userns-disabled`. Propose these for
   the independent evaluator and Pi sandbox, after testing them with trusted
   payloads. Mask the helper in the sandbox's `/usr` view as defense in depth:
   `/usr` is currently mounted wholesale, so the new `/usr/local` path would
   otherwise be visible. Masking alone is insufficient because the profile can
   be inherited and ordinary bwrap remains installed. Codex may need nested user
   namespaces for its own sandbox; do not silently disable Codex's protections
   or apply the no-nesting choice to Codex without a separate compatibility test.
   Keep Codex trials gated if both boundaries cannot coexist.
5. **Keep evaluation networking fully unshared.** The existing `--host-network`
   option is a separate, broader exposure: it adds `--share-net` for the agent,
   giving Pi shell code access to every reachable host/network service, including
   Ollama management endpoints. A userns policy fix does not narrow that access.
   Before real local-agent trials, replace that option with an Ollama-only bridge:
   a disposable host Unix-socket broker pinned to `127.0.0.1:11434`, exposed only
   to the agent sandbox, plus a small in-sandbox HTTP relay on private loopback.
   Allow only required inference/discovery routes and approved existing model
   IDs; reject management routes, arbitrary upstreams, redirects and CONNECT.
   Do not mount the socket for evaluation. This can use Python's standard library
   without changing Ollama's listener/settings or installing packages. The bridge
   needs its own size/time limits and tests; it is a proposed component, not an
   existing capability. Until then, allow offline probes only, not host-network
   agent trials under a claim of restricted network access.

Retain AppArmor enforcement, the global namespace restriction at `1`, all
existing profiles and the existing Codex configuration. Do not add global
`net_admin`/`setpcap` grants, setuid bits/file capabilities, run the workload as
root, or disable namespace protections to hide this error. The proposed targeted
allowance preserves system-wide defaults while Bubblewrap remains responsible
for the benchmark's isolation policy. Ubuntu documents per-application userns
allowances in its [AppArmor security documentation](https://documentation.ubuntu.com/security/security-features/privilege-restriction/apparmor/).

### Acceptance tests required after approval

First compile-check and load only the new profile, then run **trusted probes**,
not agents. Verify the intended label in `/proc/self/attr/current` through the
helper/child chain, no fallback capability denials, and unchanged global sysctls
and Codex profile. Do not treat successful profile loading alone as a fix.

Probe positive controls: the project is readable/writable; a host-created hidden
sentinel is readable on the host; system runtime mounts are readable but reject
writes; host listeners are reachable from host controls. Negative controls:
absolute and relative traversal and symlinks cannot read hidden tests/reference,
host credentials or unrelated workspace files; outside-work writes fail; agent
mounts contain no `/tests` or evaluator; evaluator cannot reach a temporary host
listener or external network. Verify distinct PID/network namespaces,
`NoNewPrivs`, dropped effective capabilities, descendant cleanup on timeout, and
denial of nested userns where configured. Test the positive controls to avoid
mistaking a missing file or closed listener for successful isolation.

Current `probe()` only checks several denied reads. It does not yet verify
write restrictions, networking, process teardown or runtime behavior. It also
uses an agent-style mount view for the pre-evaluation probe; add a separate
trusted evaluator-layout probe that expects `/tests` read-only and the reference
absent. No generic seccomp filter is supplied by the current runner; do not
claim Codex's independently observed seccomp protection applies to this runner.
These are validation gaps to address with the targeted runner update, not proof
that the blocked sandbox currently leaks files.

After the namespace and filesystem checks pass, test the Ollama bridge with
trusted traffic: inference route works for an allowed model, management and
unrelated host/external endpoints fail, and evaluation has no bridge. These
inference requests and actual agents remain separately approval-gated. Re-run
the reference/fixture/reset checks; preserve their existing expected results.

### Approval scope and rollback

Recommended first approval: create the dedicated helper, install/load just its
exact-path profile, update the runner selection and trusted probes, and validate
offline isolation. **No Pi/Codex agents or model requests** in that first stage.
Request separate approval for bridge implementation/traffic tests and eventual
coding trials. If new denials appear, report them before broadening policy.

Rollback is confined to unloading/removing that new profile, removing the helper
and reverting only these proposed runner changes. Leave the Codex profile and
global settings untouched. Remove the helper only after confirming it is the
new root-owned experiment file, not the distribution's bwrap. No rollback was
performed or is needed now because no repair was implemented.


## Approved implementation and validation — 2026-10-26

The user approved the exact profile contents, executable attachment and modes
before installation. Noninteractive sudo required a password, so the user ran
the reviewed `security/deploy.py install` administrator command and reported
success. Installed bytes, ownership/modes and the live process label were then
independently verified. No broader privilege or policy exception was needed.

### Exact installed policy and permissions

```text
abi <abi/4.0>,
include <tunables/global>

profile ai-lab-expense-bwrap /usr/local/libexec/ai-lab-expense-bwrap flags=(unconfined) {
  userns,
}
```

| File | Owner | Mode | Verification |
| --- | --- | --- | --- |
| `/usr/local/libexec/ai-lab-expense-bwrap` | root:binamra (0:1000) | 0750 | Regular copy of system bwrap, exact pinned SHA-256 |
| `/etc/apparmor.d/ai-lab-expense-bwrap` | root:root | 0644 | Exact reviewed profile bytes |
| `/usr/local/libexec` | root:root | 0755 | Not user-writable |
| `/usr/bin/bwrap` | root:root | 0755 | Original file, unchanged |

Source/helper SHA-256:
`e318903862396f96de3df57264e0158682b952fd3fb53ac23d876413e7b30f71`.
Installed profile SHA-256:
`1b176456401bbf23ccf5610ea6e53ea490b9de954bd13f3267bcfe2422ca4a09`.
Existing `codex-local` profile SHA-256 remains
`4d2130ef82a234fb281898b2ec6914a8de647716d9eb09c1310ebc550ca7cd3a`.
Global `kernel.apparmor_restrict_unprivileged_userns` remains **1**.
The installed policy is an unconfined-mode namespace allowance for only this
attachment; Bubblewrap supplies the filesystem/process/network restrictions.

`security/deploy.py` refuses existing destinations, verifies source/profile
bytes and root-owned non-writable parent directories, syntax-checks the policy,
creates the helper/profile with reviewed permissions, then loads only the new
profile. No distribution binary, shared bwrap profile or existing agent policy
was replaced. The namespace allowance is not a syscall filter or a guarantee
against kernel vulnerabilities.

### Implemented runner changes

- `security/isolation.py` verifies the dedicated helper's exact absolute path,
  regular-file type, root ownership, operator group, mode and digest, verifies
  policy contents/mode/ownership, and requires the global restriction to be 1.
  Missing, altered or unsafe files stop execution; PATH/system-bwrap/unsandboxed
  fallback is unavailable.
- All sandbox phases use private namespaces, `--cap-drop ALL`,
  `--disable-userns`, `--assert-userns-disabled`, disposable HOME/tmp, a cleared
  environment, no inherited stdin, and a read-only root/runtime filesystem.
  Explicit `/work`, disposable `/agent-state`, `/tmp` and `/home/agent` mounts
  are writable. The dedicated helper is masked in the sandbox's `/usr` view.
- A compatibility detail found during trusted testing: Bubblewrap 0.9.0 needs
  explicit `--unshare-user` alongside `--unshare-all` for `--disable-userns`.
  This option was added without changing policy permissions.
- The strengthened probe initially detected that bwrap's newly created empty
  root allowed ephemeral `/home` writes. It did not modify host files. Added
  `--remount-ro /` after all mounts and made only the intended HOME a separate
  writable tmpfs. All outside-write assertions then passed. A read denial on
  the helper's `/dev/null` mask is accepted as protection, as is an empty mask.
- `security/probes.py` and `probe_payload.py` check agent, evaluator and bridged
  layouts separately. The evaluator sees its tests read-only; the agent sees
  neither tests nor evaluator; neither sees the reference/host credentials.
- Every future `run` executes a fresh full offline isolation gate and then
  per-attempt agent/evaluator probes. A 20-test fake-upstream transport conformance
  gate must also pass every time. Failures or timeouts abort before agent or
  candidate execution. `validate` now also exits unsuccessfully if its hidden
  read probe fails. No cached passing result bypasses a fresh check.
- The project config template points Pi at private loopback port **11435**.
  This is a benchmark-only template, not the user's existing Pi configuration.
  Codex receives the same private endpoint through `OLLAMA_HOST` when using the
  bridge; its real client compatibility remains untested.

The current no-nested-userns policy also applies to future Codex payloads.
Codex's inner sandbox may need nested namespaces and fail. Do not disable its
sandbox or remove the outer restrictions as an automatic workaround; that would
require a new design review and approval. No Codex process was launched here.

### Implemented Ollama-only transport

`security/bridge.py` provides a short-lived host Unix-domain socket (private
0700 parent, socket 0600) and an HTTP relay on **127.0.0.1:11435 inside the private
network namespace**. The runner starts the host broker only for a future
explicitly requested `--ollama-bridge` attempt. No host TCP listener is added.
The evaluator is forbidden from mounting the broker, agent state or agent
runtimes. `--host-network` has been removed; direct host networking is rejected.

The host connection target is fixed to **127.0.0.1:11434**; client input cannot
change the host, port or scheme. Permitted upstream routes are only POST
`/v1/chat/completions` and POST `/v1/responses`, for these existing model IDs:

```text
pi-qwen35-9b-16k
pi-qwen35-9b-32k
qwen3:8b-32k
```

GET `/healthz`, `/v1/models`, `/api/tags` and `/api/version` are synthesized by
the broker without contacting Ollama. Discovery is an allowlist, not a live
model inventory; the version response is pinned and marked as broker metadata.
Reject management paths, absolute/alternative upstream URLs, CONNECT, query-path
variants, redirects, duplicate JSON keys, ambiguous body framing and unsupported
fields. Client Host/Authorization/Cookie headers are not forwarded. Limit request
bodies to 2 MiB, responses to 32 MiB, output budgets to 2,048 tokens and forwarding
time/read waits, and each broker/relay has at most eight concurrent worker
connections. Missing output budgets get the fixed 2,048 cap.

Text-only message/input validation rejects image/file URL blocks and built-in
web/MCP tools and remote JSON-schema references, preventing those inference features from becoming server-side
fetch proxies. Only function tools intended for client execution are allowed.
The protocol is deliberately narrow; an unsupported Pi/Codex schema must fail
and be reviewed rather than silently broaden routing. Real client inference
and streaming interoperability with Ollama have **not** been exercised here.

Offline bridge tests use a fake in-memory upstream for synthetic HTTP response
and stream checks. Live namespace checks use a broker whose upstream function
raises if called; only local health and denied-route probes are sent. Thus no
model was loaded, no inference request reached Ollama, and no Ollama listener,
service setting, model, driver or GPU-Unlock state was changed.

### Validation results and evidence

| Trusted check | Result |
| --- | --- |
| Helper/profile bytes, ownership, permissions and root-owned parents | Pass |
| Syntax check before loading | Pass |
| Actual sandbox label | `ai-lab-expense-bwrap (unconfined)` |
| UID, NoNewPrivs, effective/permitted capabilities | UID 1000; 1; zero/zero |
| Private user, mount, PID and network namespaces | Pass, different from host controls |
| Readable/writable project and read-only runtime/root | Pass |
| Hidden reference/tests, host credentials, absolute/traversal/symlink reads | Denied in agent view |
| Host-created readable sentinel / outside writes | Hidden, unmodified; outside writes denied |
| Evaluator layout | Tests present read-only; reference, agent state and broker absent |
| Host TCP listener | Host positive control connects; sandbox cannot connect |
| External IPv4/IPv6 routes | No route; UDP route tests send no packets; only loopback interface |
| Broker in private namespace | Local health succeeds; management routes rejected |
| Nested user namespace creation | Denied |
| Detached child after forced timeout | Heartbeat stops after namespace termination |
| Runner/transport unit tests | **32/32 pass**, fake upstream only |
| Reference / original buggy acceptance checks | **26/26** / **15/26**, exactly 11 intended failures |
| Four individual mutation checks and clean resets | Pass; original fixture unchanged |
| Agents / model inference requests | **0 / 0** |

Evidence is under `validation/security/`: `installation-verification.json`,
`summary.json`, the three layout logs/commands, detached-child cleanup logs,
`unit-tests.log`, `fixture-validation.log` and `offline-validation.log`. The final
live suite included the actual Node v24.22.1 and Pi 1.4.0 release directories
mounted read-only plus fresh agent state, without executing Node or Pi.
`validation/summary.json` also records the now-successful hidden-read check.

Re-run only trusted offline checks from this directory:

```sh
python3 -B -m unittest discover -s trusted -p 'test_*.py' -v
python3 -B runner.py validate-isolation \
  --runtime /home/binamra/.nvm/versions/node/v24.22.1 \
  --runtime /home/binamra/.pi/agent/install/releases/1.4.0
python3 -B runner.py validate
```

These commands do not invoke agents or make upstream inference requests.
Do not run `runner.py run` or agent commands until separate trial approval.

### Limitations and rollback

This remains a cooperative coding benchmark rather than a hostile-code VM.
There is no generic seccomp filter (`Seccomp: 0` was observed in the trusted
identity check), cgroup memory/process quota or disk quota. The userns policy is
an application exception; payloads are protected by dropped capabilities,
no-new-privileges, blocked nested namespaces and mount/network namespaces.
CPU/wall/address-space/output-file limits and namespace teardown are not a full
resource-exhaustion defense. Python evaluation still permits a deliberately
hostile candidate to inspect tests mounted for that evaluator or falsify its
process output; scores require review. The broker's Python server is not a
hardened multi-tenant service and model computations can still consume resources
when future inference is approved. No real-agent or real-inference compatibility
claim is made from these offline checks.

The copied helper must be reviewed/refreshed after system Bubblewrap updates.
The runner hashes both system bwrap and the dedicated copy against the pinned
digest; either mismatch fails closed. Do not replace a pinned digest without reviewing
new source bytes and re-running trusted tests.

To remove only the installed exception and helper, first stop future attempts,
then run the guarded administrator rollback:

```sh
sudo /usr/bin/python3 /home/binamra/AI-Lab/benchmarks/coding-tasks/expense-tracker/security/deploy.py rollback
```

The script verifies exact root-owned installed contents, unloads only
`ai-lab-expense-bwrap`, removes only its policy/helper and leaves the system
binary, parent directory, Codex profile and global settings alone. Keep this
benchmark's files/logs for review; the runner will then reject missing helper
instead of falling back. If installed contents differ, rollback stops for manual
review. No rollback was performed. No broader security exception was requested.


## First controlled agent trial — pi-01, 2026-10-26

**Integration failure; one trial only, no retry.** Pi 1.4.0 targeted existing
`pi-qwen35-9b-16k` (Qwen3.5 9B Q4_K_M, 16,384 context) through the restricted
broker to local Ollama 0.40.11 on the RTX 3070 Ti workstation. Required offline
isolation preflight and per-attempt agent/evaluator probes passed.

Pi's first request returned **HTTP 403: `request forbidden`** (HTML error response).
The trace records `stopReason: error`, duration 23 ms for the failed response.
No successful inference or model communication was established. The precise
rejected field/condition is not present in these logs; it was not investigated
or changed. Pi reported zero input/output/cache tokens; these are error-path
usage counters, not a successful model measurement.

Agent-phase elapsed time: **0.917050 s**, process exit **0** despite the API error.
Tool calls: **0**; no tool execution failures or visible-test execution occurred.
The runner automatically ran its independent isolated evaluator after Pi exited:
**15/26 passed**, 11 original expected failures, no test errors, evaluator exit
**1**, elapsed **0.065677 s**. This is the unchanged buggy baseline, not an agent
repair score. All project-file hashes still match the initial fixture.

Preserved: `attempts/pi-01/work/`, fresh agent state, preflight logs, agent JSONL
stdout/stderr, evaluator logs, exact commands in `result.json`, and concise
`trial-summary.json`. No further trial, broker redesign, security investigation
or configuration/system change was performed. Further integration debugging or
another attempt requires approval.


## Controlled trial pi-02 — 2026-10-26

Added only `supportsStore: false` to the benchmark Pi provider compat settings;
JSON parsing passed. Broker/security settings unchanged; `pi-01` preserved.
Exactly one new Pi 1.4.0 / Qwen3.5 9B 16K attempt ran through the required preflight.

Connection succeeded and Pi completed four tools (one bash, three reads), all
without tool errors. It then failed with **`Stream ended without finish_reason`**
(four error responses, including Pi's internal retries). No project files changed
and no visible tests ran. The attempt had already exited when a stop was attempted;
no signal was sent. No operator retry, debugging or compatibility adjustment followed.

Agent elapsed: **117.992 s**; process exit **0** despite
the trace errors. Reported tokens summed across responses: **1874 new input,
1793 cached input, 249 output; 3916 total**. Failed-stream counters
may omit generated tokens, so these are reported usage rather than complete inference
accounting. Task incomplete. Automatic independent evaluation: **15/26 pass**,
11 original failures, no test errors, **0.120 s**, evaluator exit 1.

Project, JSONL trace, preflight/evaluator logs, exact commands and summary are
preserved in `attempts/pi-02/` (`result.json`, `trial-summary.json`).


## Streaming timeout change and trial pi-03 — 2026-10-26

Changed only the Unix relay response/read idle wait to **120 seconds**. Its
connect/request-write timeout remains 10 seconds; the host broker's upstream
timeout remains 30 seconds. Existing total timeouts, size limits, routes and
sandbox policy are unchanged. Added stderr JSON metadata for read timeouts,
HTTP-stream EOF and connection closure: layer, elapsed time, byte count, status,
stage, closure reason and terminal-marker booleans only; no request/response
contents are logged. Three focused existing forwarding/redirect tests passed.

Exactly one new attempt, **pi-03**, ran through the existing mandatory preflight;
pi-01/pi-02 were preserved. Earlier streams carried valid finish reasons and
`[DONE]` through both layers. Pi completed seven tools (3 bash, 3 read, 1 edit),
with no tool-reported failures, and changed only `expense_tracker/__init__.py`.
Then **`Stream ended without finish_reason`** recurred. Broker metadata records
`read_timeout`, layer `broker`, elapsed **31.389 s**, 4,970 bytes, HTTP 200,
`finish_reason_seen=false`, `done_seen=false`. The unchanged host-upstream idle
timeout fired; the 120-second relay forwarded the premature EOF. No further
fix or troubleshooting was attempted.

The controller terminated this attempt's sandbox after the first error; Pi had
emitted an internal retry-start notice, but no operator retry/new launch occurred.
Agent elapsed **118.321 s**, exit **-15** (SIGTERM). Task **incomplete**.
Reported response totals: **3434 new input + 12700 cached input +
2227 output = 18361 tokens**; failed-stream usage may be missing.

Automatic independent evaluation could not execute the 26 test methods: package
import failed at line 61 with **`SyntaxError: Generator expression must be
parenthesized`** in Pi's edited `sum(...)` expression. Result: **0 passing**,
one unittest loader error, evaluator exit 1, **0.066 s**. Visible smoke tests
had passed 2/2 before the edit; no post-edit visible-test run completed.

Preserved in `attempts/pi-03/`: modified `work/`, agent trace/stderr, evaluator
logs, `broker-metadata.log`, controller record, focused-test log, `result.json`
and `trial-summary.json`. No additional attempts or security/model/system changes.
