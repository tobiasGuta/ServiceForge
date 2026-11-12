"""Explicit systemd runtime actions with Polkit and JobRemoved tracking.

The GUI runs unprivileged. Calls are sent to the systemd manager over D-Bus;
systemd enforces authorization. A method reply means *queued*, not completed.
"""

from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from serviceforge.backend.systemd_client import (
    BUS_NAME, MANAGER_INTERFACE, MANAGER_PATH, SystemdClient,
)
from serviceforge.models.actions import ActionOutcome, METHODS, validate_unit
from serviceforge.models.service import Scope

JobSuccess = Callable[[ActionOutcome], None]
JobError = Callable[[str], None]
MAX_WAIT_SECONDS = 90


class ServiceActions:
    """Perform one operator-approved runtime action at a time per instance."""

    def __init__(self) -> None:
        self._in_progress = False

    def execute(
        self,
        scope: Scope,
        unit_name: str,
        action: str,
        on_success: JobSuccess,
        on_error: JobError,
    ) -> None:
        """Queue an action; report JobRemoved result, never a guessed outcome."""
        if self._in_progress:
            on_error("A service operation is already in progress.")
            return
        if action not in METHODS or not validate_unit(unit_name):
            on_error("Unsupported service operation or unit name.")
            return
        if scope not in ("system", "user"):
            on_error("Unknown systemd manager scope.")
            return

        self._in_progress = True

        def connected(connection: Gio.DBusConnection) -> None:
            subscription_id: int | None = None
            timeout_id: int | None = None
            job_path: str | None = None
            early_results: dict[str, str] = {}
            finished = False

            def finish_error(message: str) -> None:
                nonlocal finished
                if finished:
                    return
                finished = True
                cleanup()
                on_error(message)

            def finish_result(result: str) -> None:
                nonlocal finished
                if finished:
                    return
                finished = True
                cleanup()
                on_success(ActionOutcome(action, unit_name, result))

            def cleanup() -> None:
                if timeout_id is not None:
                    GLib.source_remove(timeout_id)
                if subscription_id is not None:
                    connection.signal_unsubscribe(subscription_id)
                # Only one service operation can be in progress in this client.
                # Unsubscribe asynchronously; GUI must not wait on it.
                connection.call(
                    BUS_NAME, MANAGER_PATH, MANAGER_INTERFACE, "Unsubscribe",
                    None, None, Gio.DBusCallFlags.NONE, 5000, None, None, None,
                )
                self._in_progress = False

            def on_job_removed(
                _connection: Gio.DBusConnection, _sender: str, _path: str,
                _iface: str, _signal: str, parameters: GLib.Variant, _data: object,
            ) -> None:
                nonlocal job_path
                _id, removed_path, removed_unit, result = parameters.unpack()
                if removed_unit != unit_name:
                    return
                if job_path == removed_path:
                    finish_result(result)
                elif job_path is None and len(early_results) < 32:
                    # A very fast job may complete before StartUnit replies.
                    early_results[removed_path] = result

            def expired() -> bool:
                finish_error(
                    "The job result was not observed within 90 seconds. "
                    "It may still be running or finished; refresh the service "
                    "before retrying."
                )
                return GLib.SOURCE_REMOVE

            def queued(reply: GLib.Variant) -> None:
                nonlocal job_path
                value = reply.unpack()
                if len(value) != 1 or not isinstance(value[0], str):
                    finish_error("systemd returned an invalid job path.")
                    return
                job_path = value[0]
                if job_path in early_results:
                    finish_result(early_results[job_path])

            def subscribed(_reply: GLib.Variant) -> None:
                nonlocal subscription_id, timeout_id
                subscription_id = connection.signal_subscribe(
                    BUS_NAME, MANAGER_INTERFACE, "JobRemoved", MANAGER_PATH,
                    None, Gio.DBusSignalFlags.NONE, on_job_removed, None,
                )
                timeout_id = GLib.timeout_add_seconds(MAX_WAIT_SECONDS, expired)
                SystemdClient._call(
                    connection,
                    METHODS[action],
                    queued,
                    finish_error,
                    parameters=GLib.Variant("(ss)", (unit_name, "replace")),
                    flags=Gio.DBusCallFlags.ALLOW_INTERACTIVE_AUTHORIZATION,
                )

            # systemd requires Subscribe() before it emits JobRemoved signals.
            SystemdClient._call(connection, "Subscribe", subscribed, finish_error)

        def connection_error(message: str) -> None:
            self._in_progress = False
            on_error(message)

        SystemdClient._connect(scope, connected, connection_error)
