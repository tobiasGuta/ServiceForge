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
