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

## On-demand service inspection

Selecting a service opens an inspector in the existing application window.
The backend resolves the current object with `Manager.GetUnit(name)`, then
reads `org.freedesktop.systemd1.Unit` and `org.freedesktop.systemd1.Service`
using `org.freedesktop.DBus.Properties.GetAll`. Service-specific property
failure still leaves unit properties available, with a warning. Each request
has a generation counter so a stale callback cannot overwrite another
selection, manager scope, or a return to the list.

The pure-Python `ServiceDetails` model formats known properties only.
`MainPID=0` means no current PID. `ExecMainPID` may refer to a prior run;
`Requires` and `Wants` are dependencies, whereas `After` and `Before`
express ordering. The `ControlGroup` property is read from the Service
interface. Unknown values are displayed explicitly.

List and inspector views use a GTK stack so small GNOME windows remain usable.
Filter and sort are local transformations of the loaded-unit snapshot; they do
not introduce additional systemd polling.

## Overview

`models.overview.summarize_services()` counts only `ListUnits` results in
the currently selected manager. A zero failed count does **not** mean every
installed service is healthy. The Overview page consumes the same loaded-unit
snapshot as the service table, including pending/failed/error states.

## Journal reader

`backend.journal_reader.read_journal()` uses `python3-systemd`'s native Reader,
matching `_SYSTEMD_UNIT` for system services and `_SYSTEMD_USER_UNIT` plus
`_UID` for the logged-in user's services. It limits results to 200 entries
from the current boot, and reads backwards from the journal tail before
reversing for display. Some related unit-manager messages may not have these
fields, so this is not intended to exactly reproduce every `journalctl -u`
match. Some service messages are inaccessible under ordinary-user journal
permissions.

The journal operation runs through a single-worker thread executor. Callbacks
are delivered via `GLib.idle_add`, and generation counters prevent stale
results from appearing after changing service/view or refreshing. Search and
severity filtering are local transformations on the bounded snapshot.
The copy action exports only text currently displayed and is user-initiated.

## Runtime service management (experimental)

The Inspector creates no writes during normal navigation. The action policy
(`models.actions`) restricts which buttons are offered and requires a
loaded service name with conservative syntax; runtime transitions show no
buttons. `CanReload` must be explicitly true to offer Reload.

The action controller sends `StartUnit`, `StopUnit`, `RestartUnit`, or
`ReloadUnit` with job mode `replace`. The D-Bus call uses
`Gio.DBusCallFlags.ALLOW_INTERACTIVE_AUTHORIZATION`, which permits systemd
to request Polkit authentication in an ordinary user session.

Before starting an action, the client calls Manager.Subscribe, listens for
Manager.JobRemoved, and then queues the job. Completion is correlated by the
returned job path. Early job results are cached in case the signal arrives
before the D-Bus reply. Result `done` is successful job completion, but the
post-action service state is always fetched again. Timeouts are reported as
unknown outcomes, not action failures.

Unit-file enablement and masking need a distinct, tested API path; they are
not part of this initial write-enabled implementation.

## Unit lifecycle after Stop

Systemd may garbage-collect an inactive unit with no remaining references.
`GetUnit(name)` then returns `NoSuchUnit` despite the unit's file still being
installed. To represent this accurately, ServiceForge now reconciles loaded
unit records (`ListUnits`) with disk-backed service definitions
(`ListUnitFiles`), with separate explicit `loaded` flags.

For installed units that are no longer loaded, the Inspector uses the
read-only-in-effect `Manager.LoadUnit` call to resolve an in-memory Unit
object without starting it. It then reads Unit and Service properties.
A missing/deleted unit file produces a refresh hint without repeated retries.

Unloaded entries have no observed `ActiveState`; they are marked
`unloaded/unknown`, not assumed inactive. The Overview continues to count
loaded units only. The explorer's All/Loaded/Unloaded filters distinguish
these populations.

## Persistent unit-file action boundary

The `models.unit_files` policy defines conservative eligibility and
persistent-state confirmation text. `backend.unit_file_actions` performs
`GetUnitFileState` preflight, then one of `EnableUnitFiles`,
`DisableUnitFiles`, `MaskUnitFiles`, `UnmaskUnitFiles`, followed
by `GetUnitFileState` postflight. It never calls a runtime job method,
nor `Manager.Reload` without an explicit separate request.

All writes use `ALLOW_INTERACTIVE_AUTHORIZATION` to let systemd consult
Polkit, with a longer timeout for an authentication prompt. File changes
use `runtime=false` and `force=false` and carry exact unit names rather
than user-supplied absolute paths.

The Inspector has separate runtime and startup controls. It fetches fresh
file state independently of unit property inspection, so Unmask can still
be offered if a masked unit fails normal unit property inspection. Advanced
execution and dependency panels are collapsed by default. The UI never
treats a successful file change as confirmation a service started/stopped.
