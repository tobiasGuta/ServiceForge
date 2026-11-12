# Security model

ServiceForge runs as the logged-in user; the GUI must never be launched with `sudo`. It does not use a custom privileged helper.

## Current read-only milestone

- Uses Gio to call systemd's `ListUnits` and `ListUnitFiles` methods.
- Does not issue start, stop, restart, enable, disable, mask, or unmask operations.
- Does not modify unit files or disable SELinux.
- Uses timeouts, error callbacks, and stale-request guards.
- Reports missing startup state explicitly rather than fabricating a value.

## Future administrative operations

Service management calls will use systemd's native D-Bus APIs and authorization policy, including Polkit as required. All disruptive operations will need a confirmation explaining impact. A D-Bus job being accepted is not proof it completed: we must track job completion and then query the actual unit state.

Future log viewing must respect journald permissions and warn before exporting potentially sensitive logs. Future security analysis must differentiate systemd hardening configuration from evidence of exploitable vulnerabilities.

No operation should bypass existing permissions or silently weaken service hardening.

## Current journal viewer

- Journal reads are performed unprivileged with `python3-systemd` and limited
  to 200 matching entries for the current boot per request.
- System service history matches `_SYSTEMD_UNIT`; user service history
  also constrains entries to the current process UID.
- Journal access and visibility follow the operating system's existing
  permissions. ServiceForge never requests elevation to read inaccessible logs.
- Messages can contain personal information, credentials, or tokens. A user
  must explicitly click **Copy shown logs**; logs are not automatically saved
  or sent anywhere. Do not publicly share copied logs without reviewing them.
- The viewer does not silently enable journal persistence or modify logs.

## Experimental runtime controls

The Inspector now offers Start, Stop, Restart, and (only when systemd reports
`CanReload=true`) Reload. It does not write service files or implement unit
file enablement/masking. Every operation shows a confirmation dialog that
defaults to Cancel. High-impact services receive additional warnings.
Buttons are conservatively gated by last-read loaded state; the systemd
manager still determines actual applicability and whether authorization is
required. The UI uses `ALLOW_INTERACTIVE_AUTHORIZATION` to permit Polkit
authentication without elevating the GUI.

The application listens for `JobRemoved` to distinguish an accepted job
from a completed job. If the result is not observed, the UI explicitly warns
that the final state is unknown and requests a refresh. Never test these
actions on essential system units before proving behavior on disposable
services. ServiceForge does not bypass SELinux or Polkit.

The action policy also reads `Unit.CanStart`, `CanStop`, and `CanReload`.
If these properties are missing or false, the corresponding operation is not
offered. The `RefuseManualStart` and `RefuseManualStop` flags also disable
affected buttons. These checks improve safety but do not replace systemd's own
authorization and job applicability decisions.
