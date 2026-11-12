# Security model

ServiceForge runs as the logged-in user; the GUI must never be launched with `sudo`. It does not use a custom privileged helper.

## Read-only inspection and permission boundary

- Inspection uses Gio and systemd's `ListUnits`, `ListUnitFiles`,
  `GetUnitFileState` and Unit property APIs.
- The journal reader respects journald access controls.
- ServiceForge runs unprivileged; privileged operations are sent to systemd
  over D-Bus with interactive authorization allowed.
- No bespoke root helper, direct `sudo` invocation, SELinux bypass, or
  broad Polkit policy override is installed.
- Timeouts, stale-request guards and missing state handling protect the UI.
- Authorization or a successful D-Bus reply is not treated as a guarantee
  of successful runtime effects; runtime jobs are tracked to completion.

Future security analysis will distinguish hardening configuration from proof
of exploitable vulnerabilities.

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

The Inspector offers Start, Stop, Restart, and (only when systemd reports
`CanReload=true`) Reload. Persistent unit-file actions are handled by a
separate controller, not by these runtime job APIs. Every operation shows a confirmation dialog that
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

## Experimental persistent unit-file configuration

Enable/Disable/Mask/Unmask use `org.freedesktop.systemd1.Manager` via Gio.
The methods are called with `runtime=false` and (where applicable)
`force=false`, never silently replacing existing symlinks or running
`systemctl --now`. They require the normal `manage-unit-files` Polkit
authorization on system scope where policy demands it.

Eligibility requires a concrete installed unit file and a supported
`GetUnitFileState` value. Only `disabled -> enabled`,
`enabled -> disabled`, `disabled -> masked` (when inactive), and
`masked -> unmasked` are offered. Special states like `static`, `indirect`,
`alias`, `generated`, `enabled-runtime`, and `masked-runtime` are
blocked in this first release. Known core system unit names/prefixes are
also blocked from file configuration in the GUI and backend. This is
deliberately conservative and is not a comprehensive dependency safety check.

Every operation has a confirmation dialog. System-wide changes and mask
operations require typing the exact unit name. The backend rechecks
`GetUnitFileState` *immediately before* the change and verifies it *again
afterward*. An authorization refusal, state mismatch or uncertain outcome
is reported rather than silently marked successful. No automatic start/stop
operation is coupled with any file change.

The policy is not a guarantee of safety; changing startup links can impact
other services. Follow `docs/unit-file-testing.md` and
`docs/authorization-testing.md` only on disposable test units.
