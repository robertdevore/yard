# Security

Yard is a single-user utility for trusted local projects. It binds to IPv4
loopback. Every route validates the HTTP Host and any Origin header. POST
requires the page's per-server token and a JSON object with an application-level
256 KiB request bound. The dashboard uses local scripts, framing protection,
no-store responses, and a content security policy. Keep the loopback service
local when using proxies, tunnels, or container port forwarding.

The registry is a deliberate code-execution trust boundary. Only explicit
service actions execute saved commands. Keep the registry and state paths in
directories controlled by the current user. Browser writes reject a
symbolic-link registry target, and new capture uses owner-only directories
and no-follow log files. The UI requires review when adding or changing the
startup command or importing a registry. The shell runs with your user's
normal privileges. Use trusted projects and environment variable references.

HTTP probes use literal loopback addresses or `localhost`, skip Yard's own
configured listener, and use short timeouts without redirects, proxy or user
curl configuration. TCP probes use loopback. Unknown listeners are read-only
and never probed automatically. Discovery does not display arbitrary process
arguments, which may contain credentials. Configured environment values and
common secret-like environment variables are redacted from new captured logs.
Applications can still emit credentials learned from other sources, so check
log excerpts before sharing them.

Every group signal originates from an authenticated supervisor that owns the
target OS group. Even a matching prior PID gives no authority. Force Stop is
separate, needs explicit confirmation, and is blocked for sensitive groups.
Review the port, executable, and group before taking a sensitive service action.
