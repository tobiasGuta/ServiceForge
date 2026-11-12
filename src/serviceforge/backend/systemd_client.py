"""Asynchronous, read-only Gio D-Bus client for systemd managers."""

from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from serviceforge.backend.normalize import normalize_services
from serviceforge.models.service import Scope, ServiceRecord


BUS_NAME = "org.freedesktop.systemd1"
MANAGER_PATH = "/org/freedesktop/systemd1"
MANAGER_INTERFACE = "org.freedesktop.systemd1.Manager"
TIMEOUT_MS = 12000

ResultCallback = Callable[[list[ServiceRecord], str | None], None]
ErrorCallback = Callable[[str], None]


class SystemdClient:
    """Uses the system bus for PID 1 and the session bus for systemd --user."""

    def fetch_services(
        self,
        scope: Scope,
        on_success: ResultCallback,
        on_error: ErrorCallback,
    ) -> None:
        """Fetch loaded units and associated unit-file configuration.

        All operations complete asynchronously on the GLib main context.
        Neither a privilege escalation nor a service-changing method is used.
        """
        if scope not in ("system", "user"):
            on_error("Unsupported systemd manager scope")
            return
        bus_type = Gio.BusType.SYSTEM if scope == "system" else Gio.BusType.SESSION
        Gio.bus_get(
            bus_type,
            None,
            self._on_bus_ready,
            (scope, on_success, on_error),
        )

    def _on_bus_ready(self, _source: object, result: Gio.AsyncResult, context: tuple) -> None:
        scope, on_success, on_error = context
        try:
            connection = Gio.bus_get_finish(result)
        except GLib.Error as exc:
            on_error(f"Could not connect to {scope} D-Bus: {exc.message}")
            return

        self._call(
            connection,
            "ListUnits",
            lambda reply: self._on_units(
                connection, scope, reply, on_success, on_error
            ),
            on_error,
        )

    @staticmethod
    def _call(
        connection: Gio.DBusConnection,
        method: str,
        on_success: Callable[[GLib.Variant], None],
        on_error: ErrorCallback,
    ) -> None:
        def completed(source: Gio.DBusConnection, result: Gio.AsyncResult, _data: object) -> None:
            try:
                reply = source.call_finish(result)
                on_success(reply)
            except GLib.Error as exc:
                on_error(f"systemd {method} failed: {exc.message}")
            except (ValueError, TypeError, IndexError) as exc:
                on_error(f"Invalid systemd {method} response: {exc}")

        connection.call(
            BUS_NAME,
            MANAGER_PATH,
            MANAGER_INTERFACE,
            method,
            None,
            None,
            Gio.DBusCallFlags.NONE,
            TIMEOUT_MS,
            None,
            completed,
            None,
        )

    def _on_units(
        self,
        connection: Gio.DBusConnection,
        scope: Scope,
        reply: GLib.Variant,
        on_success: ResultCallback,
        on_error: ErrorCallback,
    ) -> None:
        rows = reply.unpack()[0]

        def with_files(files_reply: GLib.Variant) -> None:
            on_success(normalize_services(rows, files_reply.unpack()[0], scope), None)

        def files_unavailable(message: str) -> None:
            # Show the loaded services rather than presenting guessed states.
            on_success(normalize_services(rows, [], scope), message)

        self._call(connection, "ListUnitFiles", with_files, files_unavailable)
