# ServiceForge

**ServiceForge** is an early-stage native GNOME application for inspecting systemd services on Fedora Linux.

> **Status: early read-only prototype.** The first milestone lists *loaded* system and user services using systemd's D-Bus API. It does not start, stop, enable, disable, or otherwise modify services.

## Features in the current read-only milestone

- GTK4 and Libadwaita window using Fedora's system-provided PyGObject bindings.
- Asynchronous discovery of loaded services from the system or user manager.
- Search, quick filters, clickable column sorting, and manual refresh.
- Status icons and counts for active, inactive, and failed loaded services.
- Select a row to open the **Service Inspector**, or click **Inspect**.
- Read authoritative unit and service properties on demand, including unit-file path, PID, restart policy, execution commands, result, and dependencies.
- Clear unavailable values and error/partial-result messages.
- No root GUI, subprocess-based `systemctl` parsing, or privileged helper.

Only **loaded units** appear in this milestone. Installed but unloaded unit files will be added in a later service-discovery improvement. The inspector uses `GetUnit` plus `Properties.GetAll` for the Unit and Service interfaces, and it shows partial information when a service-specific interface cannot be read. Unit-file state is shown as `Unknown` when it cannot be mapped reliably; it is not guessed as `disabled`.

## Run from source on Fedora

```bash
sudo dnf install git python3 python3-gobject gtk4 libadwaita
git clone https://github.com/tobiasGuta/ServiceForge.git
cd ServiceForge
PYTHONPATH=src python3 -m serviceforge
```

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
- `tests/`: testable data transformation and invariants.
- `docs/`: architecture, roadmap, and security model.

## Safety and limitations

ServiceForge is not an elevated process. This milestone is strictly read-only and does not register privileged D-Bus operations. The system manager uses the system bus; the user manager uses the session bus. Error messages may reflect local systemd or D-Bus configuration.

The maintainer has confirmed the initial service table loads on Fedora (245 services in a screenshot). The updated inspector, scope switching, filters, sorting, and error-handling paths still require Fedora integration validation.

## Roadmap

1. Read-only service explorer and inspector (current; desktop validation pending).
2. Robust installed-unit discovery and signal-driven updates.
3. Authorized service actions using systemd and Polkit.
4. Journald, dependency, performance, and security inspection.
5. Tests, accessibility, packaging, and releases.

See [architecture](docs/architecture.md), [roadmap](docs/roadmap.md), and [security model](docs/security-model.md).

## License

The project's intended open-source license has not yet been finalized. Do not assume a license has been granted until a `LICENSE` file is published. A license decision is required before the first open-source release.
