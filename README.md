# Yard

**A local command center for everything running on your localhost ports.**

Yard is a single-machine dashboard that scans your computer for listening TCP
ports, shows you what is running, which project probably owns it, whether it is
healthy, and lets you safely **stop, force-stop, start, and restart** services
from one place. The metaphor: every dev server you spin up is *in the yard*.

It is built in [Kujo](https://github.com/kujolang/kujo) and runs on the Kujo
interpreter. No build step, no Node, no database, no network calls off your
machine.

```
  Yard - localhost command center
  ------------------------------------------------
  Dashboard:  http://127.0.0.1:9753
  Binding:    127.0.0.1 only (loopback)
```

## Why this exists

> Yard helps developers who run many localhost servers see what is active,
> identify port conflicts, stop zombie processes, and safely restart known
> project services from one dashboard.

If you routinely have a Next.js app, a Vite frontend, a Python API, Ollama, a
Rust service, Postgres, and three half-forgotten experiments all listening on
different ports, Yard gives you one screen that answers: *what is running, on
what port, who owns it, is it healthy, and can I safely stop or restart it?*

## What it looks like

* **Summary cards** — running ports, managed running, unknown ports, unhealthy,
  sensitive, and conflicts.
* **Service cards**, grouped by project, each showing name, port, status,
  health (status + HTTP code + response time), PID, command, URL, a
  managed/unknown badge, and a sensitive badge where relevant.
* **Actions** — Open, Copy, Start, Stop, Restart, Force, Logs, Inspect, Claim —
  shown only when they are valid for that service.
* **Controls** — search, group filter, status filter, sort (port/name/status/
  group), a refresh button, and an auto-refresh toggle.

Managed services (the ones in your config) are visually distinct from unknown
processes, which get a purple accent and a clear `unknown` badge.

---

## Running it

Yard runs on the Kujo interpreter, so you need a `kujo` binary.

```bash
# 1. Get this project
cd kujo-yard

# 2. Point Yard at your kujo binary (or put `kujo` on your PATH)
export KUJO=/path/to/kujo/target/release/kujo

# 3. (optional) put the launcher on your PATH
export PATH="$PWD/bin:$PATH"

# 4. Start the dashboard
yard
```

Then open <http://127.0.0.1:9753>.

You can always invoke it directly without the wrapper:

```bash
kujo run /path/to/kujo-yard/yard.kujo -- [command] [arguments]
```

### CLI

The default command starts the dashboard. The rest are convenience wrappers
around the exact same safe primitives:

```bash
yard                      # start the dashboard (default, port 9753)
yard serve 9000           # start on a custom port
yard scan                 # list detected services as a table
yard scan --json          # ...as JSON
yard scan --no-health     # ...skip health probes (faster)
yard open                 # open the dashboard in your browser
yard open kujo-site       # open a managed service's URL
yard start kujo-site      # start a managed service
yard stop kujo-site       # graceful stop
yard stop kujo-site --force --yes   # force kill (requires --yes)
yard restart kujo-site    # restart a managed service
yard stop-port 3000       # stop whatever listens on a port
yard config path          # print the config file path
yard config show          # dump the parsed config
yard version
yard help
```

---

## How scanning works

Yard shells out to `lsof` to enumerate listening TCP sockets:

```bash
lsof -nP -iTCP -sTCP:LISTEN +c 0
```

It parses each row into a `DetectedProcess` (port, bind address, PID, process
name, user, protocol, raw line) and de-duplicates by port (IPv4 + IPv6 rows for
the same port collapse to one). For each PID it tries `ps -o command= -p <pid>`
to recover the full command line, which improves both display and sensitive-
service detection.

If `lsof` is missing or returns nothing, Yard reports a scanner error in the UI
banner and keeps working with whatever it has — it never crashes the dashboard.

Each detected port is then:

* **matched to a managed service** by configured port,
* **labelled** if it is a recognized port (3000 → Node/React, 5432 → Postgres,
  11434 → Ollama, etc.),
* **flagged sensitive** if it is a database/model/daemon port or its command
  looks like one,
* **health-checked** (unless sensitive) with a time-boxed `curl`.

## Health checks

For each non-sensitive service Yard runs:

```bash
curl -s -o /dev/null -w '%{http_code} %{time_total}' --max-time 1 <url>
```

against the config `health` URL if present, otherwise the inferred
`http://127.0.0.1:<port>`. Results map to:

| status     | meaning                                            |
|------------|----------------------------------------------------|
| `healthy`  | HTTP 2xx/3xx                                        |
| `unhealthy`| HTTP 4xx/5xx                                        |
| `timeout`  | did not answer within the timeout                  |
| `not_http` | connected but did not speak HTTP (raw TCP service) |
| `unknown`  | not probed, refused, or health disabled            |

The HTTP status code and response time (ms) are captured when available.
Sensitive services are deliberately **not** probed over HTTP — pinging a
Postgres socket is pointless and just adds noise — so they show as `not_http`.

---

## Managed services config

Yard reads a JSON config (default `./yard.config.json`, override with
`$YARD_CONFIG`). Copy the example to get started:

```bash
cp examples/yard.config.example.json yard.config.json
```

Minimal example:

```json
{
  "services": [
    {
      "id": "kujo-site",
      "name": "Kujo Site",
      "group": "Kujo",
      "port": 3000,
      "cwd": "~/code/kujo-site",
      "start": "npm run dev",
      "health": "http://127.0.0.1:3000",
      "open": "http://127.0.0.1:3000"
    }
  ]
}
```

### Fields

| field         | required | notes                                                        |
|---------------|----------|--------------------------------------------------------------|
| `id`          | yes      | stable, unique identifier used in the API/CLI                |
| `port`        | yes      | the port Yard matches against detected listeners             |
| `name`        | no       | display name (defaults to `id`)                              |
| `group`       | no       | grouping label (defaults to `Ungrouped`)                     |
| `cwd`         | no       | working directory for `start`; `~` is expanded               |
| `start`       | no       | the **only** command Yard will run for this service          |
| `health`      | no       | health-check URL (defaults to inferred `http://127.0.0.1:port`) |
| `open`        | no       | URL for the Open action / `yard open`                        |
| `sensitive`   | no       | force-mark as sensitive (extra confirmation to stop)         |
| `tags`        | no       | array of strings, surfaced in Inspect                        |
| `description` | no       | free text, surfaced in Inspect                               |

A bare top-level array (`[ {...}, {...} ]`) is also accepted. Duplicate `id`s
and duplicate `port`s produce warnings (shown in the UI) rather than errors; the
first wins. A missing config is fine — you simply get a read-only view of
detected ports. Invalid JSON is reported as a banner, not a crash.

## Starting / stopping / restarting

* **Start** runs *only* the service's configured `start` command, in its
  configured `cwd`, detached, with stdout+stderr captured to
  `./.yard/logs/<id>.log`. The new PID, start time, and a restart counter are
  recorded in `./.yard/managed.json`.
* **Stop** sends `SIGTERM` (graceful) by default. It targets the live listening
  PID, falling back to the PID Yard recorded at start.
* **Force stop** sends `SIGKILL` and requires an explicit confirmation in the UI
  (and `--yes` on the CLI).
* **Restart** is stop-then-start, available only for managed services that have
  a `start` command. It bumps the restart counter.
* **Unknown processes** can be stopped or force-stopped by PID, but never
  started or restarted (Yard has no command for them).

State and logs live under `./.yard` by default (override with `$YARD_DIR`).

---

## Safety model

Yard is local command-and-control, so it is conservative by design:

1. **Loopback only.** The server binds to `127.0.0.1`, never `0.0.0.0`. It is
   not reachable from other machines.
2. **Action token.** Every destructive (`POST`) endpoint requires a per-session
   token that is embedded in the dashboard page. Same-origin scripts can act; a
   malicious cross-origin page can neither read nor guess the token, so it can't
   forge stop/start requests.
3. **No arbitrary commands.** The browser can never send a command to run. Start
   and restart execute *only* the `start` string from your local config file.
   There is no shell passthrough anywhere in the API.
4. **Graceful by default.** Stops are `SIGTERM` first; `SIGKILL` is a separate,
   explicit action.
5. **Force requires confirmation.** Force-stop always needs an explicit confirm
   (UI modal / `--yes`).
6. **Sensitive services are guarded.** Postgres, MySQL, Redis, MongoDB, Docker
   daemons, Ollama, Elasticsearch, RabbitMQ, etc. (by port or command, or
   `"sensitive": true` in config) require extra confirmation before stopping and
   are never HTTP-probed.
7. **Restart is managed-only.** Unknown processes are never restarted.
8. **No destructive defaults.** Nothing is stopped, killed, or started unless
   you ask for it.
9. **Shell-safe.** Config values are POSIX single-quote escaped before use, so
   metacharacters can't break out of the intended command.

You should be able to leave Yard running locally without fear.

## Architecture

```
yard.kujo            entrypoint (args -> cli.main -> exit code)
bin/yard             bash launcher (kujo run wrapper)
src/
  util.kujo          shared helpers (no I/O)
  knownports.kujo    known-port map + sensitive-service rules
  ports.kujo         lsof scanner + parser (read-only)
  config.kujo        config load/validate
  health.kujo        curl-based health probing + status mapping
  state.kujo         managed-process state + log capture (./.yard)
  process.kujo       the ONLY module that signals/starts/stops processes
  status.kujo        fuses scan + config + state + health into ServiceStatus
  api.kujo           JSON endpoint logic (pure-ish, testable)
  web.kujo           the single-page dashboard (self-contained HTML/CSS/JS)
  serve.kujo         HTTP routes, 127.0.0.1 binding, token enforcement
  cli.kujo           command dispatch
tests/yard_test.kujo hand-rolled test harness
```

The layering keeps future features (Docker integration, MCP/Ollama detection, a
port-conflict resolver, "stop all managed", WebSocket live updates, persisted
history) additive: new detectors feed `status.kujo`, new actions go through
`process.kujo`, new endpoints wrap `api.kujo`.

## API

All responses are JSON except `GET /`.

| method | path                               | notes                                  |
|--------|------------------------------------|----------------------------------------|
| GET    | `/`                                | the dashboard HTML                     |
| GET    | `/api/summary`                     | summary cards + config health          |
| GET    | `/api/services`                    | full ServiceStatus list + summary      |
| GET    | `/api/ports`                       | raw detected listeners                 |
| GET    | `/api/services/:id/logs`           | captured logs for a managed service    |
| POST   | `/api/services/:id/start`          | start a managed service                |
| POST   | `/api/services/:id/stop`           | stop (`{force, confirm}` in body)      |
| POST   | `/api/services/:id/restart`        | restart (`{confirm}` in body)          |
| POST   | `/api/processes/:pid/stop`         | stop an unknown process                |
| POST   | `/api/processes/:pid/force-stop`   | force-stop an unknown process          |

GET endpoints accept `?health=0` to skip health probing. POST bodies must
include `"token": "<session token>"`.

## Tests

```bash
kujo run tests/yard_test.kujo
# or
KUJO=/path/to/kujo ./tests/run.sh
```

The suite (72 checks) covers config parsing (valid, missing, invalid JSON, bare
array, duplicate ids/ports, missing required fields), managed/unmanaged matching
by port, known-port detection, sensitive-service detection (by port and by
command), health-status parsing, the `lsof` parser (including dedupe and
garbage tolerance), and the summary aggregation.

## Troubleshooting

* **"lsof unavailable" banner** — install `lsof`, or check permissions. Yard
  only reads listening sockets; it never needs root.
* **A managed service shows `stopped` but the port is busy** — something Yard
  didn't start is on that port. That is exactly the `conflict` count; Inspect
  the unknown process on the same port.
* **Start "succeeds" but the service isn't up** — check
  `./.yard/logs/<id>.log`; the process likely exited immediately (bad command,
  wrong `cwd`, missing dependency).
* **Health shows `not_http` for a web app** — it may not be answering on the
  inferred URL; set an explicit `health` URL in config.
* **Health shows `timeout`** — the service is slow or hung; Yard caps probes at
  1s so the dashboard stays responsive.
* **403 on an action** — the page's action token expired (server restarted).
  Reload the dashboard to pick up the new token.

## Known limitations

* TCP listeners only (no UDP); macOS/Linux only (relies on `lsof`/`ps`/`curl`).
* The HTTP server is single-threaded; a self-referential health check (a managed
  service whose health URL points at Yard itself) will wait out the 1s timeout.
* No process *tree* management — stopping a service signals the PID Yard started
  or the listening PID, not arbitrary descendants.
* Logs are captured only for services Yard started; externally-started processes
  have no logs to show.
* The action token lives for the server session; restarting Yard invalidates
  open dashboard tabs until reloaded.

## Suggested next improvements

* Docker / container-aware detection and controls.
* MCP-server and Ollama/LM Studio specific recognizers.
* A port-conflict resolver ("free port 3000").
* "Stop all managed" and "stop all unknown Node servers" batch actions.
* Project-folder detection to auto-suggest config entries (richer "Claim").
* WebSocket live updates instead of polling.
* Persisted history / per-project scorecards and log search.
