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
