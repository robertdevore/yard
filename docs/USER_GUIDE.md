# Yard user guide

Install Yard using the [README instructions](../README.md#install-and-open).
Run `yard` to open it. Bookmark the loopback URL or run `yard` again to reuse
the instance. On macOS you can pin a Shortcut that runs your installed
`~/.local/bin/yard` with Kujo and Python on its PATH. Yard leaves login items
under your control.

## Add an application

Select **Add Service** and enter its name, directory, and startup command.
Set the application port if it has one. For a browser application, enter a
dashboard URL and optionally a health URL. Review the command and save.
Use **Discovery** to inspect a listening process or scan a known project
directory for manifest suggestions. Review and complete the suggested fields
before registering them.

| Example | Project directory | Startup command | Health and open |
| --- | --- | --- | --- |
| Kujo RepoRadar | `~/2026/reporadar` | `kujo run src/main.kujo serve 8080` | `http://127.0.0.1:8080/` |
| Node.js app | Directory containing a reviewed package `dev` script | `npm run dev` | Enter the address the reviewed script actually binds |
| Python static preview | Directory containing files to preview | `python3 -m http.server 8000 --bind 127.0.0.1` | `http://127.0.0.1:8000/` |

For workers without a network listener, leave the port empty and select a
process health check. In Advanced Settings you can set a required executable,
environment reference names, and shutdown or startup deadlines.

Click the star beside a service name to add or remove a favorite. The default
**Favorites first** sort keeps starred services at the top. Yard saves your
favorites in the registry.

## Control and troubleshoot

- **Start** runs the saved command and waits for the configured readiness
  check. **Open** opens the application's browser page when available.
- **Stop** gracefully shuts down a Yard-owned group. Open the row's details
  or **More actions** and select **Restart** to stop and relaunch it.
- **Recent logs** shows output captured by Yard. Refresh the excerpt in the
  details panel. A process that exited immediately usually records its
  startup error there. Check the directory, port, executable, and environment
  references or run `yard doctor` for diagnostics.
- **External listener** means a process occupies the port outside verified
  Yard ownership. Inspect the listener and use its original launcher if it
  needs to stop.
- **Remove** removes the registry entry. Stop a Yard-owned service before
  removing it. A removed external entry returns to Discovery.

Closing the browser leaves managed applications running. A foreground Yard
server stops with Ctrl+C. Start Yard later with the same registry and state to
see the recovered applications.
