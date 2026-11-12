"""Asynchronous, persistent systemd unit-file changes (never sudo, never force).

Method signatures:
  EnableUnitFiles(as,b,b) -> (b,a(sss))
  DisableUnitFiles(as,b) -> (a(sss))
  MaskUnitFiles(as,b,b) -> (a(sss))
  UnmaskUnitFiles(as,b) -> (a(sss))
These calls do not start/stop/restart services.
"""

from collections.abc import Callable

import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from serviceforge.backend.systemd_client import SystemdClient
from serviceforge.models.actions import validate_unit
from serviceforge.models.service import Scope
from serviceforge.models.unit_files import (
    FILE_METHODS, EXPECTED_STATES, FileActionOutcome,
)


Success = Callable[[FileActionOutcome], None]
Error = Callable[[str], None]
AUTHORIZATION_TIMEOUT_MS = 180000


def parameters_for_file_action(
    action: str, unit_name: str,
) -> GLib.Variant:
    """Always persistent (runtime=False) and non-forcing (force=False)."""
    if action not in FILE_METHODS or not validate_unit(unit_name):
        raise ValueError("Unsupported unit-file operation")
    if action in ("enable", "mask"):
        return GLib.Variant("(asbb)", ([unit_name], False, False))
    return GLib.Variant("(asb)", ([unit_name], False))


def unpack_changes(reply: GLib.Variant, action: str) -> tuple[
    bool | None, tuple[tuple[str, str, str], ...],
]:
    """Validate the reply rather than confusing queueing and file changes."""
    unpacked = reply.unpack()
    if action == "enable":
        if len(unpacked) != 2 or not isinstance(unpacked[0], bool):
            raise ValueError("Unexpected EnableUnitFiles response")
        install_info = unpacked[0]
        raw = unpacked[1]
    else:
        if len(unpacked) != 1:
            raise ValueError("Unexpected unit-file response")
        install_info = None
        raw = unpacked[0]
    if not isinstance(raw, (list, tuple)):
        raise ValueError("Missing unit-file changes")
    changes: list[tuple[str, str, str]] = []
    for row in raw:
        if (
            not isinstance(row, (list, tuple)) or len(row) != 3
            or not all(isinstance(value, str) for value in row)
        ):
            raise ValueError("Malformed unit-file changes")
        changes.append(tuple(row))
    return install_info, tuple(changes)


class UnitFileActions:
    """One change at a time; preflight and postflight state are authoritative."""

    def __init__(self) -> None:
        self._in_progress = False

    def get_state(
        self, scope: Scope, unit_name: str,
        on_success: Callable[[str], None], on_error: Error,
    ) -> None:
        if scope not in ("system", "user") or not validate_unit(unit_name):
            on_error("Invalid service name or manager scope")
            return

        def connected(connection: Gio.DBusConnection) -> None:
            def succeeded(reply: GLib.Variant) -> None:
                values = reply.unpack()
                if len(values) != 1 or not isinstance(values[0], str):
                    on_error("systemd returned an invalid unit-file state")
                    return
                on_success(values[0])

            SystemdClient._call(
                connection, "GetUnitFileState", succeeded, on_error,
                parameters=GLib.Variant("(s)", (unit_name,)),
            )

        SystemdClient._connect(scope, connected, on_error)

    def execute(
        self, record_scope: Scope, unit_name: str, action: str,
        expected_state: str,
        on_success: Success, on_error: Error,
    ) -> None:
        if self._in_progress:
            on_error("Another unit-file operation is still in progress")
            return
        if (
            record_scope not in ("system", "user")
            or not validate_unit(unit_name)
            or action not in FILE_METHODS
            or expected_state != EXPECTED_STATES[action]
        ):
            on_error("Unsupported operation or stale unit-file state")
            return

        self._in_progress = True
        completed = False

        def error_once(message: str) -> None:
            nonlocal completed
            if completed:
                return
            completed = True
            self._in_progress = False
            on_error(message)

        def connected(connection: Gio.DBusConnection) -> None:
            def verified_state(current: str) -> None:
                nonlocal completed
                if completed:
                    return
                completed = True
                self._in_progress = False
                on_success(
                    FileActionOutcome(
                        action, unit_name, expected_state, current,
                        changes, install_info,
                    )
                )

            def after_write(reply: GLib.Variant) -> None:
                nonlocal changes, install_info
                if completed:
                    return
                try:
                    install_info, changes = unpack_changes(reply, action)
                except (ValueError, TypeError) as exc:
                    error_once(
                        "systemd returned an unexpected reply after the operation. "
                        f"The configuration may have changed. Refresh to verify: {exc}"
                    )
                    return
                self.get_state(
                    record_scope, unit_name, verified_state,
                    lambda message: error_once(
                        "Systemd accepted the file operation, but its final "
                        "state could not be verified. Refresh before retrying. "
                        + message
                    ),
                )

            def preflight(current: str) -> None:
                if completed:
                    return
                if current != expected_state:
                    error_once(
                        f"The unit-file state changed from {expected_state!r} "
                        f"to {current!r}. No change was requested; refresh "
                        "and confirm again."
                    )
                    return
                SystemdClient._call(
                    connection, FILE_METHODS[action],
                    after_write,
                    error_once,
                    parameters=parameters_for_file_action(action, unit_name),
                    flags=Gio.DBusCallFlags.ALLOW_INTERACTIVE_AUTHORIZATION,
                    timeout_ms=AUTHORIZATION_TIMEOUT_MS,
                )

            changes: tuple[tuple[str, str, str], ...] = ()
            install_info: bool | None = None
            self.get_state(record_scope, unit_name, preflight, error_once)

        SystemdClient._connect(record_scope, connected, error_once)
