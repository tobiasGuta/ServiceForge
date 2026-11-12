# Architecture

ServiceForge is a modular, unprivileged Python desktop application.

## Layers

1. **UI**: GTK4 and Libadwaita in `src/serviceforge/ui`; never executes privileged commands.
2. **Backend**: Gio D-Bus calls to `org.freedesktop.systemd1.Manager`.
3. **Normalization**: pure Python conversion to immutable `ServiceRecord` objects.
4. **Models**: typed service state with optional values for unknown properties.

`SystemdClient.fetch_services()` is asynchronous and reports errors through callbacks on the GLib main context. Each UI refresh has a sequence ID so late replies cannot overwrite newer manager selections.

## Two different systemd managers

- **System services**: `Gio.BusType.SYSTEM`, typically managed by PID 1.
- **User services**: `Gio.BusType.SESSION`, managed by the user's systemd instance.

Both use `org.freedesktop.systemd1` and `/org/freedesktop/systemd1`.

## Unit data

The MVP calls `ListUnits` and `ListUnitFiles`. The first returns loaded units; the second returns unit-file paths and enablement states. The UI intentionally does not combine runtime state with startup configuration.

Some loaded instances, aliases, generated units, and transient units may not have an exact basename match in `ListUnitFiles`. Their startup state is shown as **Unknown** rather than guessed. A later iteration should reconcile file entries more precisely and support installed-but-unloaded unit discovery.

## Future boundaries

Administrative writes belong in a dedicated action controller, with confirmation, Polkit, and asynchronous systemd job tracking. Journal access, performance inspection, and security assessments will be separate read-only modules. GUI responsiveness and clear error handling are non-negotiable.
