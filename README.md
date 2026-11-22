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
> identify untracked and unknown listeners, stop zombie processes, and safely restart known
> project services from one dashboard.

If you routinely have a Next.js app, a Vite frontend, a Python API, Ollama, a
Rust service, Postgres, and three half-forgotten experiments all listening on
different ports, Yard gives you one screen that answers: *what is running, on
what port, who owns it, is it healthy, and can I safely stop or restart it?*

## What it looks like

* **Summary cards** — running ports, managed running, unknown ports, unhealthy,
  sensitive, untracked, and stopped services.
* **Service cards**, grouped by project, each showing name, port, status,
  health (status + HTTP code + response time), PID, command, URL, a
  managed/unknown badge, and a sensitive badge where relevant.
* **Actions** — Open, Copy, Start, Stop, Restart, Force, Logs, Inspect, Claim —
  shown only when they are valid for that service.
* **Controls** — search, group filter, status filter, sort (port/name/status/
  group), a refresh button, and always-on auto-refresh.

Managed services (the ones in your config) are visually distinct from unknown
processes. A managed listener that Yard did not start or cannot match to its
stored PID gets a neutral `untracked` badge; this is informational, not a port
conflict.

---

## Running it

Yard runs with `kujo run` on macOS and Linux. Use Kujo 1.5.0 or newer with
`lsof`, `ps`, `curl`, and the standard POSIX shell utilities on your PATH.

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
kujo run /path/to/kujo-yard/yard.kujo [command] [arguments]
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
yard stop-port 3000       # stop all detected listeners on a port
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
name, user, protocol, raw line). The dashboard and scan output show one row per
port and look up each displayed PID's command once per scan. Process actions
use all detected listeners, including PIDs hidden by the display deduplication.

An empty successful scan is normal. When `lsof` fails or returns incomplete
results, the dashboard shows the rows it could read alongside a scanner banner.
Process actions require a complete scan. `yard scan` exits 1 on scanner failure
and the JSON output includes `scan_error` alongside any partial results.

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
curl -q -g -s -o /dev/null -w '%{http_code} %{time_total}' --proto '=http,https' --max-time 1 -- <url>
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
Yard reports sensitive listeners as `not_http` without probing them. The
dashboard skips probes to its own loopback address and port. Turn off health
checks for a fast scan that only reads listener and process metadata.

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
| `open`        | no       | HTTP(S) URL for the Open action / `yard open`                |
| `sensitive`   | no       | force-mark as sensitive (extra confirmation to stop)         |
| `tags`        | no       | optional labels retained in the parsed config                |
| `description` | no       | free text, surfaced in Inspect                               |

A bare top-level array (`[ {...}, {...} ]`) is also accepted. Duplicate `id`s
and duplicate `port`s produce warnings (shown in the UI) rather than errors; the
first wins. With a missing config, Yard still shows and can stop detected
listeners. An invalid config is reported in the dashboard and CLI scan output.

## Starting / stopping / restarting

* **Start** launches the configured command in `cwd`, with stdout and stderr
  captured in `./.yard/logs/<id>.log`. The configured port must be free. The
  log is replaced on each launch. Yard records the PID and process start time
  in `./.yard/managed.json`.
* **Stop** sends `SIGTERM` to the sole detected listener on the configured port.
  When the port is empty, Yard can stop a process it started if the recorded
  PID and process start time still match. For older entries that stored only a
  PID, wait for the process to listen or stop it directly outside Yard.
* **Force stop** sends `SIGKILL` and requires confirmation in the UI or `--yes`
  on the CLI.
* **Restart** validates the launch settings, sends `SIGTERM`, waits for the old
  process to exit, and checks the port before launching the replacement. When
  the process fails to exit within the wait window, Yard reports the failure
  and leaves the replacement unstarted. A successful restart increments the
  counter once.
* **Stop by PID or port** applies to currently detected TCP listeners. If a
  managed port has multiple distinct listeners, service-level stop and restart
  ask you to inspect them before acting.

CLI and dashboard actions share a lock and atomically update managed state.
State and logs live in `./.yard` by default. Point `YARD_DIR` at a trusted,
user-owned directory, and use the same path for the CLI and dashboard.
If managed state is unreadable, preserve the file and restore a valid copy
before running managed actions. Use a foreground executable for `start`. For
setup or pipelines, point `start` at a script that uses `exec` for the final
service so Yard tracks its PID.

---

## Safety model

Yard is local command-and-control, so it is conservative by design:

1. **Loopback only.** The server binds to `127.0.0.1`, never `0.0.0.0`. It is
   not reachable from other machines.
2. **Local HTTP authority and action token.** Connect via `127.0.0.1` or
   `localhost` at the configured port. Requests with an Origin header must
   match that address. Every action requires the session token embedded in the
   dashboard. The dashboard refuses framing.
3. **No arbitrary commands.** The browser can never send a command to run. Start
   and restart execute *only* the `start` string from your local config file.
   There is no shell passthrough anywhere in the API.
4. **Graceful by default.** Stops are `SIGTERM` first; `SIGKILL` is a separate,
   explicit action.
5. **Force requires confirmation.** Force-stop always needs an explicit confirm
   (UI modal / `--yes`).
6. **Sensitive services are guarded.** Postgres, MySQL, Redis, MongoDB, Docker
   daemons, Ollama, Elasticsearch, RabbitMQ, etc. (by port or command, or
   `"sensitive": true` in config) require extra confirmation before stopping or
   restarting. Protection applies across every detected port belonging to the
   same PID, including for health probes.
7. **Restart is managed-only.** Unknown processes are never restarted.
8. **No destructive defaults.** Nothing is stopped, killed, or started unless
   you ask for it.
9. **Local config is trusted code.** The `start` command uses shell syntax. Yard
   quotes filesystem paths separately and uses HTTP(S) URLs for probes and
   browser actions.

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
tests/yard_test.kujo module regression tests
tests/integration.sh isolated CLI, process, and loopback HTTP tests
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

The summary and service list accept `?health=0` to skip probing. POST bodies
must include `"token": "<session token>"`. The logs endpoint returns up to
300 lines from the most recent 256 KiB, with `truncated` set when it returns
an excerpt.

## Tests

```bash
kujo run tests/yard_test.kujo
# or
KUJO=/path/to/kujo ./tests/run.sh
```

For state, process control and the real HTTP routes, run the isolated
integration suite.

```bash
./tests/integration.sh
```

The module tests cover config validation, sensitivity, health interpretation,
listener parsing and display deduplication. The integration suite uses disposable
processes and a loopback dashboard to check concurrent starts, restart failures,
stale state, request guards, health probes and log bounds.

## Troubleshooting

* **"listener scan failed" banner** — install `lsof`, or check permissions. Yard
  only reads listening sockets; it never needs root.
* **A managed service shows `untracked`** — a process is listening on its
  configured port, but its PID does not match Yard's stored state. This is
  common for services started outside Yard and is not, by itself, a conflict.
  Use Inspect to verify the process when its identity is unexpected.
* **Start "succeeds" but the service isn't up** — check
  `./.yard/logs/<id>.log`; the process likely exited immediately (bad command,
  wrong `cwd`, missing dependency).
* **Health shows `not_http` for a web app** — it may not be answering on the
  inferred URL. Set an explicit `health` URL in config.
* **Health shows `timeout`** — the service is slow or hung; Yard caps probes at
  1s so the dashboard stays responsive.
* **403 on an action** — the page's action token expired (server restarted).
  Reload the dashboard to pick up the new token.

## Known limitations

* TCP listeners only (no UDP); macOS/Linux only (relies on `lsof`/`ps`/`curl`).
* Health probes run serially and each can take up to 1s. Large fleets with
  several unresponsive listeners can take multiple seconds to scan.
* Yard signals individual processes. Service wrappers should forward signals or
  replace themselves with the service using `exec`.
* PID and start-time comparisons precede the OS signal. PID reuse between a
  check and signal remains possible. Keep Yard scoped to your own local services.
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
