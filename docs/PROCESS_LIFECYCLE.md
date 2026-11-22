# Process lifecycle

Yard's Kujo backend validates the registry and coordinates actions under a
shared state lock. A small Python standard-library helper supplies POSIX
session creation, group signaling, and bounded log capture.

1. **Start** checks the directory, explicit executable and environment
   requirements, listener conflicts, and any prior ownership record. Yard saves
   a randomly addressed supervisor record before launch. The helper runs the
   configured shell command inside a fresh process session with stdin closed.
2. **Readiness** verifies the supervisor response. For a port-based service,
   Yard also requires an observed listener inside the owned group before
   applying the configured health check. Portless workers require a stable
   process. A deadline or early exit produces a diagnostic and retains logs.
3. **Stop** contacts the verified supervisor over a private Unix socket.
   The supervisor signals its own group with SIGTERM. Yard waits for member
   exit and checks port release. After a timeout the dashboard records the
   failure and allows a safe retry.
4. **Restart** uses the same graceful shutdown path before starting again.
   The counter advances after readiness. A failed shutdown leaves the existing
   service in place. A failed start is shown with the available logs.
5. **Force Stop** uses SIGKILL only after confirmation against the selected
   group. Sensitive groups support confirmed graceful actions. Force Stop is
   disabled for them.

## Ownership and reconciliation

| Status | Evidence |
| --- | --- |
| Registered | A definition exists in the registry |
| Yard-owned | A live supervisor proves ownership using the configuration's private socket capability |
| External listener | A listener occupies a registered port and Yard has no verified ownership there |
| Unregistered | A listener's port is absent from the registry |
| Unknown | The scan or identity check could not establish status |

Process groups survive browser and Yard server restarts. The saved socket
capability allows the next Yard server to reconcile an existing group.
The supervisor itself holds the group identity while delivering a signal.
A recorded PID, port match, command match, and discovery registration each
provide insufficient evidence for sending a signal. If custody is lost while
a group may remain, Yard refuses to start a duplicate and asks you to inspect
the service through its original launcher.

Keep the command and its workers in the foreground process group. Work that
starts a separate process group or session can escape supervision. Use a foreground mode for
frameworks and daemons. A registered service can run after a browser tab
closes or the dashboard server stops. Existing processes and registry
definitions remain visible when Yard starts again.

The Kujo process and helper exchange bounded JSON over standard input and
output. New state records keep the private credentials and original
sensitivity classification needed for later control. The launcher passes the
full launch configuration only to the supervisor that starts the service.
A failed process census keeps the supervisor available for authorized
recovery and leaves the dashboard status uncertain. Readiness uses a
monotonic elapsed-time budget and requires a complete listener scan for
port-based services.
