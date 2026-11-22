# Yard hardening audit

2026-11-22 · Fix mode

## Repository and baseline

Yard is a Kujo CLI and loopback dashboard for inspecting TCP listeners and
controlling development services. The pass used the local `ruff-yard` checkout
of `robertdevore/yard` on `main`. The working tree started clean at
`82474c0b9ac4a6942141284d803894c223f8a2fb`. The verified implementation ends
at `f74871594de2e880500810addf49514996e5ab0a`.

Yard has no Kujo package dependencies or asset build. Its runtime dependencies
are Kujo, `lsof`, `ps`, `curl`, and the macOS/Linux shell utilities. The
checked-in launcher, default and example configs, module harness, dashboard
JavaScript, and runtime API boundaries were in scope.

Before edits, the module suite passed 89 checks on Kujo 1.5.0 and 1.9.0.
`bash -n bin/yard tests/run.sh` and a live macOS
`./bin/yard scan --no-health --json` passed. The baseline had no end-to-end
controls suite, CI workflow, build pipeline, or agent/tool manifest.

## Findings

| ID | Priority | Area | Finding and evidence | Action and status |
| --- | --- | --- | --- | --- |
| Y1 | P0 | HTTP authority | `serve.kujo` bound to loopback but accepted any HTTP authority. The page embedded the control token and lacked framing protection. | Validate Host and Origin on every route, generate tokens using OS entropy, deny framing, and mark responses as non-cacheable. Verified over HTTP. |
| Y2 | P0 | Process selection | The port-deduplicated display scan also authorized stop, and CLI and HTTP independently classified sensitive targets. A PID listening on another sensitive port could be evaluated from an unrelated row. | Separate display rows from control selection. Check all listeners and config for the PID, reject ambiguous service-level controls, and reject PID actions outside observed TCP listeners. Verified with disposable listeners. |
| Y3 | P0 | State and restart | The state writer deleted the current file before replacement. Concurrent CLI/dashboard mutations could race. Restart discarded stop errors and started before confirming the process exited. | Lock managed actions, strictly load and atomically save state, check launch settings, and wait for termination before starting a replacement. Verified with concurrent launches, invalid state and a TERM-resistant process. |
| Y4 | P0 | Stale PIDs | Managed state stored only a PID. Stop fell back to that number when a service had no listener. | Store and check process start time and require observable evidence for legacy records. A race remains between the final process check and numeric signal delivery. |
| Y5 | P1 | Logs | The logs endpoint used `read_file` on the entire accumulating file and then clipped lines. | Tail at most 256 KiB and return up to 300 lines with `truncated` metadata. Verified with a 290,000-byte line plus trailing content. |
| Y6 | P1 | Scan cost | `status.kujo` repeated `ps` per port, repeatedly searched arrays, and split each row with per-character Kujo operations. | Cache the command per display PID within each scan, index port membership, and use native whitespace splitting. Verified with byte-identical fixture output and subprocess counts. |
| Y7 | P1 | Health and UI load | Health probes used a shell command and could inherit curl directives. Dashboard timers could issue overlapping scans, including a self-probe. A plain object could not safely group arbitrary labels. | Use bounded argv execution for HTTP(S), skip recognized own-server targets, coalesce refreshes, and render arbitrary group keys. Verified in HTTP and headless Chrome tests. |
| Y8 | P2 | Input and diagnostics | Unexpected scan results could be treated as an empty healthy scan. CLI parsing accepted misspelled switches. Config IDs could stringify non-strings and accept reserved path segment names. | Fail safely on scan errors and incomplete results, reject invalid arguments and IDs, report partial scan errors in CLI JSON, and restrict Open to HTTP(S). Verified in module and integration suites. |

## Compatibility and efficiency

- Successful CLI scan JSON and the first-listener-per-port shape remain
  compatible. Scanner failures now exit 1. JSON still carries the partial
  payload and adds `scan_error` in that case.
- The HTTP routes and successful action envelopes are retained. Clients must
  use the supported loopback authority. The logs response adds `truncated`.
  PID actions require a detected listener. Managed control refuses shared-port
  ambiguity and cannot use a legacy PID alone to signal a non-listener.
- The state file gains `process_started`. Yard reads older entries and
  continues to operate on detected listeners. The command-line flags and
  environment variables are documented in the README. Invalid explicit ports
  and unknown flags now return usage errors. No dependency or package upgrades
  were required.
- No-health benchmark on macOS with Kujo 1.5.0. An archived baseline and the
  implementation used the same simulated `lsof` output of 120 distinct
  IPv4 ports and 12 shared PIDs. The mock `ps` returned `node fixture.js` and
  recorded each invocation. Each run executed
  `/usr/bin/time -lp ./bin/yard scan --no-health --json` with the mocks first
  on PATH, a missing config, and isolated state. Ports were `20000+i` and
  PIDs were `1200+(i%12)` for `i=0..119`. The fixture outputs compared
  byte-for-byte with `cmp`.

| Metric | Before | After |
| --- | ---: | ---: |
| Median wall time, five runs | 5.02 s | 0.91 s |
| Wall time range | 4.01–6.80 s | 0.88–0.96 s |
| `ps` calls per scan | 120 | 12 |
| Log read size | Entire file | Up to 256 KiB collected |

No process memory, browser rendering performance, or model-token measurements
were taken.

## Checklist coverage

| Phase | Evidence and disposition |
| --- | --- |
| 0–1 · Inventory and baseline | Inspected every source module, the launchers, package manifest, configs, docs, test fixtures, and history. Recorded the baseline above. |
| 2 · Complexity | Consolidated CLI and HTTP service actions and shared sensitivity checks. Removed unused display helpers with no callers. |
| 3–4 · Runtime and resources | Measured scan work, bounded log reads and probe execution, and checked state-lock lifetime and child descriptor handling. |
| 5–6 · Agent context and output | Yard ships neither model prompts nor an MCP/tool manifest. Reviewed JSON, browser polling, and failure output. Raw and inspected command detail remain available. The summary route remains the smaller payload, and polling no longer stacks scans. |
| 7–9 · Errors, trust, concurrency | Reviewed local HTTP, user config, URL/process execution, state, PID selection, and logging boundaries. Covered failures, restart behavior, and same-state concurrency with disposable fixtures. |
| 10–11 · Contracts and supply chain | Checked CLI, JSON and on-disk compatibility. Native Kujo primitives and existing OS tools cover the changes. |
| 12–13 · Regression gates | Added six module checks and a deterministic local integration runner. The repository currently has no remote CI configuration. |
| 14–15 · Docs and operation | Updated the README for startup, ownership, confirmations, scan exit codes, log caps, and verification commands. Verified JSON output through the launcher. |
| 16 · Dead weight | Removed unused formatting helpers. Retained the raw API, existing launcher, sample config, and status controls. |
| 17–18 · Implementation and verification | Source and regression coverage committed. Final checks and the repeated benchmark are listed below. |

## Remaining work

- **P1, pending runtime support** · Yard cannot atomically couple PID identity
  verification to numeric signal delivery. A recycled PID in this interval,
  or a reuse with the same second-resolution `ps` timestamp, may evade the
  check. Investigate whether Kujo can expose an identity-bound process signal
  on the supported platforms. This pass verified stale-state rejection on
  macOS and did not attempt to reproduce the narrow OS race.
- **Needs more evidence** · Linux execution was not verified on this host.
  The local Docker daemon was unavailable.
- **Needs more evidence** · Health probes are serial. A bounded parallel
  design would need measurements on a fleet with slow listeners. The
  no-health benchmark intentionally excludes endpoint latency.

## Verification receipt

| Command or check | Result |
| --- | --- |
| `./tests/run.sh` with PATH Kujo 1.5.0 | 95 passed |
| `KUJO=/Users/robertdevore/2026/Kujolang/kujo-repos/kujo/target/release/kujo ./tests/run.sh` | 95 passed on Kujo 1.9.0 |
| `./tests/integration.sh` with each of the above runtimes | Both passed. Includes `node --check` for embedded JavaScript when Node is present. |
| `bash -n bin/yard tests/run.sh tests/integration.sh` | Passed |
| `./bin/yard scan --no-health --json` | Passed against actual macOS listeners. Checked services and summary via `jq`. |
| Headless Chrome through Playwright against an isolated Yard instance | Passed. Exercised a `constructor` group, the logs modal, and queued health refresh while the prior request was in flight. |
| Five-run scan benchmark and `cmp` | Passed with the fixture above. |
| `git diff --check` | Passed |
| ShellCheck, Linux execution | Unavailable on this host. |
