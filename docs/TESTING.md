# Testing

Run these from the Yard checkout.

```sh
./tests/run.sh
./tests/integration.sh
python3 tests/browser.py
python3 tests/local_apps.py
python3 tests/benchmark.py
```

The Kujo module suite checks listener parsing, configuration compatibility,
status summaries, health interpretation, and the dashboard template.
The integration suite uses disposable processes and loopback ports to verify
the request guards, registry round trips, damaged configuration, recovery,
launch diagnostics, health checks, and lifecycle ownership. Its Node test uses
npm only when available. Temporary files and test applications are isolated
from the user's configuration.

The browser test requires Playwright and Chromium. It uses the installed
Google Chrome on macOS if present, or Playwright's Chromium. Set
`YARD_CHROMIUM` to select another Chromium executable and `YARD_SCREENSHOTS`
to redirect screenshots. It exercises keyboard focus and Escape, search,
filters, sorting, Add/Edit/Remove, log display, discovery and external
registration, launch/open/restart/stop, failure feedback, and the narrow layout.

The local applications test is optional and needs the repositories in the
[inventory](LOCAL_SERVICE_INVENTORY.md). Override the default `~/2026` root with
`YARD_PROJECTS_HOME`. It uses disposable app state and the declared service
ports. Existing listeners cause Yard to fail safely instead of taking control.

The benchmark times the first dashboard response, five HTML reads, and five
uncached status refreshes. It samples the idle Kujo dashboard process with
`ps`. The large fixture contains 40 stopped definitions and 24 listeners that
accept TCP connections without answering HTTP. Results depend on the host's
listener population and load. See the
[implementation report](IMPLEMENTATION_REPORT.md) for recorded measurements.
