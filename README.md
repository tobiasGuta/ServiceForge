# ServiceForge

**ServiceForge** is an early-stage native GNOME application for inspecting systemd services on Fedora Linux.

> **Status: experimental development preview.** The application explores loaded services, displays an Overview, inspects unit properties, and reads accessible journal entries. It now also includes *opt-in* Start, Stop, Restart and Reload actions for eligible loaded services. These actions change service runtime state; test only on disposable units before relying on them.

## Features in the current development preview

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
- Explicitly confirmed Start, Stop, Restart, and Reload runtime controls when eligible.
- Systemd D-Bus job tracking: an action is not marked successful when merely queued.
- Existing systemd/Polkit authorization; no root GUI or custom privileged helper.
- Enable/Disable and Mask/Unmask are **not yet implemented**.

Only **loaded units** appear in this milestone. Installed but unloaded unit files will be added in a later service-discovery improvement. The inspector uses `GetUnit` plus `Properties.GetAll` for the Unit and Service interfaces, and it shows partial information when a service-specific interface cannot be read. Unit-file state is shown as `Unknown` when it cannot be mapped reliably; it is not guessed as `disabled`.

## Run from source on Fedora

```bash
sudo dnf install git python3 python3-gobject gtk4 libadwaita python3-systemd
git clone https://github.com/tobiasGuta/ServiceForge.git
cd ServiceForge
PYTHONPATH=src python3 -m serviceforge
```

From the service table, click **Overview** for the dashboard. To inspect a unit, select it and click **Inspect** (or activate its row), then click **Logs** for journal history.

### Experimental service actions

For a safe hands-on test, follow [the disposable user-service test guide](docs/testing.md).

Inside the Inspector, eligible loaded services show **Start**, **Stop**, **Restart**, and sometimes **Reload**. Reload is only offered if the service's `Unit.CanReload` is true. Buttons require refreshed service details, and **every operation requires confirmation**. Critical services receive additional warnings. System services may prompt for Polkit authentication. ServiceForge tracks systemd's `JobRemoved` result and refreshes the unit; it does not assume queueing is success.

**For your first test use a disposable service you created**, not NetworkManager, SSH, your display manager, logind, auditing, or other critical system components. Stop/restart can interrupt dependent services. This release has not yet been tested for live write operations on the maintainer's Fedora laptop. For systemd and Polkit semantics, see `docs/security-model.md`.

The journal viewer uses native `python3-systemd` bindings. It reads **up to 200 matching entries from the current boot**, not a live stream or full history. It now also matches selected systemd-manager lifecycle messages about units (such as messages tagged `UNIT` or `USER_UNIT`), rather than requiring a unit process itself to log. Journal permissions and missing fields can limit what appears. If journal support is not installed, the service explorer still works and the Logs view shows an error. No process is started with `sudo`.

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

ServiceForge is not an elevated process. Inspection and journal features are read-only. The new runtime management buttons explicitly request authorized D-Bus operations only after user confirmation. The system manager uses the system bus; the user manager uses the session bus. Error messages may reflect local systemd or D-Bus configuration.

The maintainer has confirmed the service table, Overview, Inspector and journal viewer working on Fedora in screenshots. Runtime service actions and expanded lifecycle journal matching still require hands-on Fedora validation.

## Roadmap

1. Read-only explorer, inspector, overview, and recent journal history (current; desktop validation pending).
2. Robust installed-unit discovery, real-time notifications, and live journal streaming.
3. Test Start/Stop/Restart/Reload authorization and job tracking against disposable units; then add Enable/Disable/Mask/Unmask.
4. More advanced dependency, performance, and security inspection.
5. Tests, accessibility, packaging, and releases.

See [architecture](docs/architecture.md), [roadmap](docs/roadmap.md), and [security model](docs/security-model.md).

## License

The project's intended open-source license has not yet been finalized. Do not assume a license has been granted until a `LICENSE` file is published. A license decision is required before the first open-source release.
