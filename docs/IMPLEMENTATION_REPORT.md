# Yard 2.0 implementation report

## Result

Yard is installed at `~/.local/bin/yard` on the audited Mac. Run `yard` from
any directory to open [the loopback dashboard](http://127.0.0.1:9753).
The default registry is `~/.config/yard/yard.config.json`. No macOS login item
was configured.

The dashboard adds editable registry entries, favorites, search, filters,
process and log details, and separate listener and project discovery. Start
reports readiness, Stop checks shutdown and port release, and Restart waits for
shutdown before relaunch. A private supervisor verifies ownership across Yard
process restarts and signals only its own process group. Legacy raw listener
controls now return a read-only explanation.

Yard retained its Kujo CLI and HTTP server, loopback request guard, `lsof`
parser, status and health interpretation, known-port safeguards, and atomic
local state. Python's standard library supplies POSIX supervision and batches
OS probes. The browser uses local static assets.

## Applications

The [inventory](LOCAL_SERVICE_INVENTORY.md) records the local checkouts and
observed listeners, with unverified launch settings identified. The active
registry contains these definitions.

| Registration | Control |
| --- | --- |
| RepoRadar · port 8080 | Kujo launch and HTTP readiness, verified with a disposable database |
| Cron Control Surface · port 8765 | Kujo launch and HTTP readiness, verified with disposable home state and manual run disabled |
| SignalBox, CMS API, Watchdog, Yard, Strata, Snips, Snips Helper | Existing observational registry rows preserved |

The two executable definitions were saved through the normal registry API.
Neither application was left running after the isolated smoke tests.

## Verification

| Command or workflow | Result |
| --- | --- |
| `./tests/run.sh` | 95 Kujo checks passed |
| `./tests/integration.sh` | 10 disposable API, registry, and lifecycle tests passed |
| `python3 tests/browser.py` | Chromium passed launch, open, stop, restart, logging, add/edit/remove, external listener registration, discovery, keyboard focus, and responsive checks |
| `python3 tests/local_apps.py` | RepoRadar and Cron Control Surface returned HTTP 200 with verified ownership and stopped gracefully |
| `yard doctor --json` | Passed with nine registered applications and the default Yard listener |
| `bash -n`, `node --check static/yard.js`, and `git diff --check` | Passed |

The lifecycle tests verified that an externally started process stays running
after registry changes or attempted control. They also exercised missing
commands, working directories, runtime and environment dependencies,
unhealthy and slow HTTP health endpoints, failed graceful stop, group cleanup,
and Yard restart while a service remained running. The browser workflow
opened the fixture page after readiness and stopped the same owned service.

Screenshots were taken with disposable services at
[1280 × 850](screenshots/yard-laptop.png) and
[390 × 844](screenshots/yard-narrow.png).

## Performance

Benchmark environment was macOS 26.6.2 on x86-64 with Kujo 1.5.0 and
Python 3.10.5. Cold time measures server launch through the first HTML
response. HTML and uncached status are medians of five requests. RSS and
CPU are one idle sample of the Yard dashboard process.

| Fixture | Cold startup | HTML | Uncached refresh | Idle RSS | Idle CPU |
| --- | ---: | ---: | ---: | ---: | ---: |
| One stopped service | 231.0 ms | 4.7 ms | 719.0 ms | 41.5 MiB | 0.0% |
| 64 services, including 24 unresponsive HTTP listeners | 213.6 ms | 4.3 ms | 3,255.9 ms | 46.2 MiB | 0.0% |

## Limits

Yard manages foreground applications that stay within their supervised
process group. Docker internals, detached daemons, system services, and
ambiguous listeners require their own control tools. Process argument
strings are withheld from browser discovery because they can contain
credentials. Cached snapshots and per-probe deadlines bound polling.
Lifecycle requests are synchronous and can defer an HTTP refresh until
the configured action finishes. Health history lives in the browser session.
The suite ran on macOS. Linux was outside this verification run.

## Git

The branch is `yard-2.0`, based on `e58cd5a`.

| Commit | Change |
| --- | --- |
| `53fbaf9` | Document the verified local inventory |
| `7fd29d8` | Supervise owned groups and persist the registry |
| `faec508` | Build the dashboard and launcher |
| `4de2080` | Harden reconciliation and state errors |
| `a425a05` | Detach the launcher and index service lookups |
| `99c57a0` | Verify lifecycle and local application integration |
| Document Yard 2.0 and its verification | Publish this report, guides, and screenshots in the branch |

Changed paths are grouped below.

- Installation and package — `.gitignore`, `README.md`, `bin/yard`,
  `bin/supervisor.py`, `kujo.toml`.
- Kujo modules — `src/api.kujo`, `src/cli.kujo`, `src/config.kujo`,
  `src/discovery.kujo`, `src/health.kujo`, `src/ports.kujo`,
  `src/process.kujo`, `src/registry.kujo`, `src/serve.kujo`,
  `src/state.kujo`, `src/status.kujo`, `src/supervisor.kujo`, `src/web.kujo`.
- Dashboard — `static/index.html`, `static/yard.css`, `static/yard.js`.
- Verification — `tests/benchmark.py`, `tests/browser.py`,
  `tests/fixture_server.py`, `tests/integration.py`, `tests/integration.sh`,
  `tests/local_apps.py`, `tests/support.py`, `tests/yard_test.kujo`.
- Documentation — `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_REPORT.md`,
  `docs/LOCAL_SERVICE_INVENTORY.md`, `docs/PROCESS_LIFECYCLE.md`,
  `docs/SECURITY.md`, `docs/SERVICE_REGISTRY.md`, `docs/TESTING.md`,
  `docs/USER_GUIDE.md`, and the two screenshots under `docs/screenshots/`.

The working tree is clean. The home registry and installed launcher symlink
are local files outside Git.
