# Service registry

The registry is JSON. The format accepts an object with a `services` array or
a legacy top-level array. Edits keep the original shape, unrecognized fields,
and top-level metadata. Yard shares an advisory state lock with lifecycle
actions, serializes writes through a lock beside the registry, and replaces the
registry atomically. A corrupt file is displayed as an error
and preserved for correction or restoration. An interrupted write leaves the
previous registry in place. Duplicate IDs or ports are flagged, and older
registries retain the first matching row until corrected.

## Paths

`yard --config PATH --state PATH <command>` takes precedence over `YARD_CONFIG`
and `YARD_DIR`. The defaults are `~/.config/yard/yard.config.json` and
`~/.config/yard/state`. Shell-relative override paths are evaluated when you
invoke Yard. A service's relative `cwd` is evaluated against the registry
directory. `YARD_PORT` changes the dashboard port, with an explicit
`yard serve PORT` taking precedence.

Use the same config and state paths in the CLI and browser. Give each separate
registry its own state directory. New ownership records bind their service ID
to the absolute registry path used at launch, so a second registry cannot
control that ID through the same state directory. An existing
`./yard.config.json` can stay where it is if you pass `--config`. Copy it to the
default location to migrate, adjusting relative working directories to match
the new location. Old restart records and logs are readable. Yard 2.0 requires
a live supervisor for actions and cannot inherit ownership from old PID-only
records. For earlier Yard 2.0 supervisor records, restore the original
startup command, working directory, and port before stopping a service if those
fields have changed. Stop managed services before moving their registry or state.

## Fields

| Field | Meaning |
| --- | --- |
| `id` | Stable unique identifier with letters, digits, dots, underscores, or hyphens |
| `name`, `description`, `group` | Display name, short description, and grouping |
| `port` | Optional unique TCP port from 1 to 65535 |
| `cwd` | Project directory, with `~/` expansion and registry-relative path support |
| `start` | Reviewed POSIX shell command that runs the app in the foreground |
| `open` | Optional HTTP(S) dashboard URL |
| `health_type` | `http`, `tcp`, `process`, or `none`. Defaults to HTTP when a health URL exists, TCP with a port, and Process otherwise |
| `health`, `expected_status` | HTTP loopback endpoint and optional exact status. The default is HTTP 200–399 |
| `probe_timeout_ms` | 100–800 ms, default 400 ms |
| `startup_timeout`, `shutdown_timeout` | 1–10 seconds, default 3 seconds each |
| `runtime`, `executable` | Runtime display label and a command or executable path to verify before starting |
| `env` | Array of required environment variable names inherited from the Yard process |
| `enabled`, `favorite`, `sensitive` | Management switch, favorite, and additional stop protections |

Port-only rows can be used to observe a known endpoint. Services without a
port need a startup command. Disabling management prevents Start and Restart
while retaining Stop for an already-owned group. The registry supports up to
250 entries through the UI. The legacy `tags` and `stop` fields are preserved.
The supervisor handles shutdown through OS signals.

## Edit and exchange

Use **Add Service** or **Edit Service** to review and save fields. Open
**Registry** to download the JSON, validate an import, or import new entries.
Import merges services and rejects collisions. Registration requires a separate
Start action. Stop a Yard-owned service before changing its port or removing
its entry. Removing an externally started entry leaves its listener running.
Application files belong to the underlying application.

Store secrets in the environment. The registry and the dashboard display
startup commands and URLs, so use environment references there.
