# Local service inventory

Inspected on macOS with Kujo 1.5.0. Paths below are relative to `~/2026`.
“Observed” means the listener was present during the initial inspection.
Registration decisions distinguish source inspection from execution.

| Application | Project | Runtime and launch | Port and readiness | Management and dependencies |
| --- | --- | --- | --- | --- |
| RepoRadar | `reporadar` | Kujo. From the checkout, `kujo run src/main.kujo serve 8080` | 8080, HTTP `/`, confirmed in the server routes | Foreground dashboard. Uses SQLite at `~/.reporadar.db` by default, with `REPORADAR_DB` available for isolated tests. Register. |
| Cron Control Surface (Cron Troll Center) | `crontrol-surface` | Kujo. From the checkout, `./run.command` execs the interpreter | 8765, HTTP `/`; configurable through `CRON_CONTROL_PORT` | Foreground dashboard. Uses per-user cron and SQLite state. Startup requires no cron edits. Leave manual job execution disabled and register. |
| Yard | `Kujolang/kujo-repos/yard`, also `ruff-yard` | Kujo and Bash launcher. `bin/yard serve 9753` | 9753, HTTP dashboard at `/` | Control center itself. Preserve its existing read-only registry entry. |
| Watchdog | `Kujolang/kujo-repos/watchdog` | Kujo telemetry dashboard. The checkout cwd matched a live listener | 7700 observed | Preserve existing read-only registry entry. Active instance launch environment and data dependencies were unverified. |
| SignalBox | `Kujolang/kujo-repos/signalbox` | Kujo. The checkout cwd matched a live listener | 4848 observed | Preserve existing read-only registry entry. Active instance launch environment was unverified. |
| Kujo RAG | `Kujolang/kujo-repos/rag` | Kujo. The checkout cwd matched a live listener | 8787 observed | Retrieval server. Index and provider configuration of the live instance were unverified. Leave discovery-only. |
| AI Chat | `Kujolang/kujo-repos/ai-chat` | Node and Python processes had the checkout cwd | 4174 and 8645 observed | Multiple components and per-user state. Leave discovery-only. |
| PostgreSQL and Ollama | System/application processes | PostgreSQL daemon and Ollama desktop/model service | 5432 and 11434 observed | Sensitive shared infrastructure. Leave discovery-only. |

The existing sample also lists CMS API, Strata, Snips and Snips Helper.
Keep those entries observational until their launch settings and shutdown paths
have been verified independently. No discovered startup script was executed
during inventory collection.
