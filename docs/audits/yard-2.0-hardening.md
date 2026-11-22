# Yard 2.0 repository hardening

Fix mode · 2026-11-22 · `robertdevore/yard` · branch `yard-2.0`

The starting checkout was clean at `6fb73d4826bec2334610a069de7d0a6ee7299c05`.
The verified implementation commit is `8630b0cea1b86b5a29300d13ce47d91369f5a767`. Yard is a local service
registry and supervisor with a loopback dashboard. It uses Kujo and a
Python standard-library helper. POSIX locks, process groups, `lsof`, `ps`,
`curl`, and Git provide the system integration. RepoRadar, Cron Control Surface,
and the isolated Node and Python test services exercise the launch contract.
The original dashboard styling and the official-release review hold are
preserved. The [earlier repository audit](repository-hardening.md) remains
available as historical evidence.

## Baseline

Kujo 1.5.0 on macOS 26.6.2 passed 95 module checks, 10 integration tests, and the
Chromium workflow. The first benchmark invocation timed out waiting for its
disposable HTTP fixture. The same benchmark passed from an archived checkout
at the starting SHA. The fixture driver now surfaces startup exit output and
verifies that the answering instance has the expected registry. The failure
cause was not established.

## Findings and fixes

| ID | Priority | Area | Finding and evidence | Action and status |
| --- | --- | --- | --- | --- |
| Y20-1 | P0 | Registry isolation | Lifecycle actions indexed state by service ID alone. Separate registries sharing state could operate on the same supervised job. Writes to the same registry using different state directories took different locks. | Bind new ownership records to their registry path, guard lifecycle, edits, and log reads, and serialize writes beside the registry. Require matching launch fields for previous records. Concurrent and cross-registry regression tests passed. |
| Y20-2 | P0 | Process failure handling | A failed group census could end a supervisor or be interpreted as an empty group. Partial listener scans could qualify a service for readiness. Clock changes could skew startup and refresh deadlines. | Preserve the authenticated socket after a failed census, report uncertain status, require a complete listener scan, and use monotonic deadlines. State persistence failure now stops the action. Verified with mocked census failure, readiness, and existing restart tests. |
| Y20-3 | P1 | Helper transport | Supervisor launch data and capabilities were serialized as command arguments. Status sent full launch specifications and received the entire process table. | Exchange bounded JSON on standard input and output, keep only recovery fields in new durable records, and return only listener and relevant child metadata from status. Keep on-disk and in-flight legacy socket protocol compatibility. |
| Y20-4 | P1 | Launcher concurrency | Concurrent cold starts could spawn multiple dashboard candidates and truncate the shared startup log. | Lock per state directory and port, then recheck the listener before starting. Three concurrent cold launches passed against one dashboard. |
| Y20-5 | P1 | TCP readiness | An IPv6-only listener was probed at IPv4 loopback. | Select the loopback address family from the observed listener. The disposable IPv6 service verified readiness and shutdown. |
| Y20-6 | P2 | Repair and refresh | Validation depended on the installed registry. POST handlers parsed JSON twice. In-flight status data could be reused after a mutation, and browser health history retained removed IDs. | Make validation independent, parse and authorize POST once, request a fresh snapshot after writes, and prune old health history. The validation and browser regressions passed. |

Other supporting changes remove duplicate registry parsing from lifecycle
actions, reuse the port-label table, preserve the launch-time sensitivity flag,
and keep redacted log writes within the existing retention limit.

## Coverage and remaining work

| Phase | Evidence |
| --- | --- |
| 0 · Repository | Inspected the launcher, Python helper, Kujo modules, browser assets, test fixtures, package and dependency metadata, and operational documentation. |
| 1 · Baseline | Ran unit, integration, browser and benchmark commands. Preserved the original audit and measured the archived revision separately. |
| 2 · Complexity | Eliminated duplicate request and registry parsing and repeated port-label table construction. |
| 3 · Runtime | Compared the unchanged benchmark fixture and reduced process snapshot transfer. |
| 4 · Resources | Kept subprocess input/output bounded, pruned removed browser history, and retained capped logs. |
| 5 · Agent context | No prompts, provider requests, model integrations, replay, MCP or tool schemas in this repository. Existing JSON CLI output remains available. |
| 6 · Output | Snapshot returns relevant metadata, startup fixture errors expose useful diagnostics, and log limits remain in place. |
| 7 · Failures | Supervisors, census uncertainty, partial listener scans, and state writes fail with diagnostic evidence. Independent validation remains available for repair. |
| 8 · Security | Reviewed loopback Host/Origin checks, action tokens, request sizes, file modes, symlink handling, health destinations, and subprocess boundaries. Kept process ownership and group confirmation in place. |
| 9 · Concurrency | Covered state/registry locks and concurrent dashboard cold starts. Authentication still belongs to each live supervisor socket. |
| 10 · Contracts | Public route names, CLI options and registry JSON shape stay compatible. Diagnostics and correctness change as described below. |
| 11 · Dependencies | Kept the Kujo and Python runtime baseline and system tools. Added no third-party dependencies. |
| 12 · Verification | Added behavioral cases for registry serialization, cross-registry ownership, census failures, registry repair, and IPv6-only readiness. |
| 13 · Ratchets | Existing deterministic module and integration entry points now cover the new cases. No machine-dependent timing gate added. |
| 14 · Documentation | Updated the lifecycle and registry guides with the ownership, transport, and recovery behavior. |
| 15 · Agent experience | JSON doctor and scan remain stable. Specific registry and census diagnostics reduce the need to inspect raw process output. |
| 16 · Dead weight | Removed evidenced duplicate parsing and helpers. Kept established aliases and legacy PID/state compatibility paths. |
| 17–18 · Fix and verification | Applied the evidence-backed fixes above and ran the receipts below. |

The launcher coordinates starts using the same state directory. Use a
distinct state directory for a separate registry, and stop its supervised
jobs before moving or renaming that registry. Earlier Yard 2.0 launch records
need the original command, directory, and port to prove identity. External
process controls remain read-only. No registry migration or environment
variable change is required. Legacy socket payloads are understood by the
upgraded client. The Python helper's private invocation protocol changed
from arguments to standard input. Restart the dashboard when upgrading an
in-place checkout so the Kujo process and helper use the same protocol.

P2 · Synchronous actions can still occupy Kujo's HTTP request loop until an
action completes, as documented in the original implementation report.
Needs more evidence · Linux verification and benchmark variability under
parallel host activity. No cross-repository fixes are required for this pass.

## Performance and verification

The unchanged fixture measures a single stopped service and a 64-service
registry with 24 unresponsive listeners. Times are milliseconds. HTML and
refresh are medians of five requests. RSS is one idle sample in KiB.
Asset size, builds, model tokens, and wider CPU profiling were outside this
measurement. A same-host snapshot sample with 19 requested listener PIDs
reduced serialized process rows from 771 to 19, and response bytes from
106,463 to 2,063. Listener metadata was preserved in the sampled results.

| Workload | Cold before → after | HTML before → after | Uncached refresh before → after | Idle RSS before → after |
| --- | ---: | ---: | ---: | ---: |
| One stopped service | 139.4 → 144.7 | 2.0 → 2.4 | 432.8 → 501.9 | 39,812 → 36,132 |
| 64 services, 24 unresponsive | 137.6 → 138.8 | 2.8 → 2.4 | 2,349.1 → 2,466.9 | 49,848 → 43,896 |

The first comparison showed smaller idle RSS in both cases and higher
uncached refresh medians. Initial refresh sample ranges were 391.4–455.0 ms
before and 491.1–527.4 ms after for one service, and 2,305.4–2,683.8 ms
before and 2,431.3–2,508.7 ms after for 64 services. A second back-to-back
run recorded 516.5 → 541.7 ms for one service and 2,540.0 → 2,467.9 ms
for 64 services. One-service refresh was slower in both comparisons. The
mixed workload varied in both directions. Idle RSS was smaller in both
comparisons, and the idle CPU samples remained at 0.0%.

## Verification receipt

| Command | Final result |
| --- | --- |
| `bash -n bin/yard`, `bash -n tests/integration.sh` | Passed |
| `python3 -m compileall -q bin/supervisor.py tests` and `node --check static/yard.js` | Passed |
| `./tests/run.sh` | 95 checks passed |
| `./tests/integration.sh` | 15 integration tests passed |
| `YARD_SCREENSHOTS=/tmp/yard-hardening-ui-verified python3 tests/browser.py` | Passed the desktop, narrow viewport, and lifecycle workflow |
| `python3 tests/local_apps.py` | RepoRadar and Cron Control Surface both reached HTTP 200 and stopped |
| `python3 tests/benchmark.py` | Both fixtures completed |
| `yard doctor --json` | Verified the upgraded loopback instance and nine registered services |
| `git diff --check` | Passed |
