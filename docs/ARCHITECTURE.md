# Architecture

`bin/yard` resolves paths, starts or reuses the local HTTP process, and opens the
browser. It invokes `yard.kujo`, which hands arguments to `src/cli.kujo`.
The Kujo backend owns the application and HTTP routes. Static HTML, CSS, and
JavaScript render the interface without a build step.

| Component | Responsibility |
| --- | --- |
| `src/serve.kujo`, `src/api.kujo` | Loopback routes, request guards, action tokens, and response envelopes |
| `src/config.kujo`, `src/registry.kujo` | Validation, compatible reads, and locked atomic edits |
| `src/state.kujo`, `src/process.kujo` | Durable ownership records, lifecycle ordering, and log reads |
| `src/ports.kujo`, `src/discovery.kujo` | TCP listeners, process inspection, and explicit project scans |
| `src/status.kujo`, `src/health.kujo` | Ownership-aware statuses and bounded registered health checks |
| `src/supervisor.kujo`, `bin/supervisor.py` | POSIX session bridge, private supervisor sockets, bounded capture, and batched OS probes |
| `src/web.kujo`, `static/` | Locally served dashboard, controls, forms, and polling |

The browser polls every four seconds when visible. The server coalesces health
reads for one second. On-demand discovery scans the selected directory and
immediate subdirectories for manifests without running scripts. The dashboard
labels those results as candidates. Listener inspection checks its PID start
time around the observation and shows a Git root when the current process
working directory supports one.

## HTTP routes

| Method and path | Response |
| --- | --- |
| `GET /`, `GET /yard.css`, `GET /yard.js` | Browser dashboard and static assets |
| `GET /api/identity` | Yard version, registry and state paths for launcher matching |
| `GET /api/services`, `GET /api/summary` | Snapshot or aggregate, with optional `?health=0` |
| `GET /api/ports` | Detected listeners |
| `GET /api/registry` | Registry data with preserved legacy fields |
| `POST /api/registry` | `add`, `edit`, `remove`, `validate`, or `import` |
| `GET /api/discovery/processes/:pid` | Best-effort process cwd, start time and Git root |
| `POST /api/discovery/projects` | Read-only project candidates for a supplied `root` |
| `GET /api/services/:id/logs` | Up to 300 recent lines from a bounded log excerpt |
| `POST /api/services/:id/start`, `/stop`, `/restart` | Action using the registered service ID and its ownership record |

Send `application/json` POST requests with the current page's `token`.
Stop accepts a boolean `force` and explicit boolean `confirm`. Browser
confirmations include the inspected group as `target`. The old explicit
listener-stop endpoints and `yard stop-port` return a read-only explanation.
