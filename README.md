# ServiceForge

**ServiceForge** is an early-stage native GNOME application for inspecting systemd services on Fedora Linux.

> **Status: early read-only prototype.** The application explores *loaded* system/user services via D-Bus, displays a snapshot overview, inspects unit properties, and reads recent journal entries when accessible. It does not start, stop, enable, disable, or otherwise modify services.

## Features in the current read-only milestone

- GTK4 and Libadwaita window using Fedora's system-provided PyGObject bindings.
- Asynchronous discovery of loaded services from the system or user manager.
- Search, quick filters, clickable column sorting, and manual refresh.
- Status icons and counts for active, inactive, and failed loaded services.
- Select a row to open the **Service Inspector**, or click **Inspect**.
- Read authoritative unit and service properties on demand, including unit-file path, PID, restart policy, execution commands, result, and dependencies.
- Clear unavailable values and error/partial-result messages.
- **Overview** page: counts from the current loaded-unit snapshot and direct links to failed services.
- **Logs** view from the inspector: up to 200 readable journal entries from the current boot.
- Journal message search, severity filtering, refresh, and an explicit copy action.
- No root GUI, subprocess-based `systemctl` parsing, or privileged helper.

Only **loaded units** appear in this milestone. Installed but unloaded unit files will be added in a later service-discovery improvement. The inspector uses `GetUnit` plus `Properties.GetAll` for the Unit and Service interfaces, and it shows partial information when a service-specific interface cannot be read. Unit-file state is shown as `Unknown` when it cannot be mapped reliably; it is not guessed as `disabled`.

## Run from source on Fedora

```bash
sudo dnf install git python3 python3-gobject gtk4 libadwaita python3-systemd
git clone https://github.com/tobiasGuta/ServiceForge.git
cd ServiceForge
PYTHONPATH=src python3 -m serviceforge
```

From the service table, click **Overview** for the dashboard. To inspect a unit, select it and click **Inspect** (or activate its row), then click **Logs** for journal history.

The journal viewer uses native `python3-systemd` bindings. It reads **up to 200 matching entries from the current boot**, not a live stream or full history. Its user-service filter selects `_SYSTEMD_USER_UNIT` and the current UID; system-service entries select `_SYSTEMD_UNIT`. Journal permissions and missing fields can limit what appears. If journal support is not installed, the service explorer still works and the Logs view shows an error. No process is started with `sudo`.

Run pure-Python tests:

```bash
python3 -m unittest discover -s tests -v
```

Use a regular user account. Do not run the GUI with `sudo`.

## Project structure

- `src/serviceforge/app.py`: application entry point.
- `src/serviceforge/ui/main_window.py`: native service explorer UI.
- `src/serviceforge/backend/systemd_client.py`: asynchronous Gio D-Bus client.
- `src/serviceforge/backend/normalize.py`: pure-Python normalization of systemd responses.
- `src/serviceforge/models/service.py`: immutable service record.
- `src/serviceforge/models/overview.py`: snapshot counts and failed services.
- `src/serviceforge/models/journal.py`: safe journal formatting/filtering.
- `src/serviceforge/backend/journal_reader.py`: bounded native journald access off the UI thread.
- `src/serviceforge/ui/overview_view.py`: dashboard.
- `src/serviceforge/ui/journal_view.py`: read-only log viewer.
- `tests/`: testable data transformation and invariants.
- `docs/`: architecture, roadmap, and security model.

## Safety and limitations

ServiceForge is not an elevated process. This milestone is strictly read-only and does not register privileged D-Bus operations. The system manager uses the system bus; the user manager uses the session bus. Error messages may reflect local systemd or D-Bus configuration.

The maintainer has confirmed the initial service table and improved filter/status UI on Fedora (245 loaded services in screenshots). The new overview, service journal, and their error-handling paths still require hands-on Fedora desktop validation.

## Roadmap

1. Read-only explorer, inspector, overview, and recent journal history (current; desktop validation pending).
2. Robust installed-unit discovery, real-time notifications, and live journal streaming.
3. Authorized service actions using systemd and Polkit.
4. More advanced dependency, performance, and security inspection.
5. Tests, accessibility, packaging, and releases.

See [architecture](docs/architecture.md), [roadmap](docs/roadmap.md), and [security model](docs/security-model.md).

## License

The project's intended open-source license has not yet been finalized. Do not assume a license has been granted until a `LICENSE` file is published. A license decision is required before the first open-source release.
