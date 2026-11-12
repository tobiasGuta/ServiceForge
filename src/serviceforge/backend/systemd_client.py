"""Read-only, asynchronous Gio D-Bus integration with systemd managers."""

from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from serviceforge.backend.normalize import normalize_services
from serviceforge.models.details import ServiceDetails
from serviceforge.models.service import Scope, ServiceRecord


BUS_NAME = "org.freedesktop.systemd1"
MANAGER_PATH = "/org/freedesktop/systemd1"
MANAGER_INTERFACE = "org.freedesktop.systemd1.Manager"
UNIT_INTERFACE = "org.freedesktop.systemd1.Unit"
SERVICE_INTERFACE = "org.freedesktop.systemd1.Service"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
TIMEOUT_MS = 12000

ListCallback = Callable[[list[ServiceRecord], str | None], None]
DetailCallback = Callable[[ServiceDetails], None]
ErrorCallback = Callable[[str], None]


def unpack_properties(reply: GLib.Variant) -> dict[str, Any]:
    """Convert a D-Bus GetAll '(a{sv})' response to regular Python values."""
    outer = reply.unpack()
    if not isinstance(outer, tuple) or len(outer) != 1:
        raise ValueError("Unexpected D-Bus properties response")
    raw = outer[0]
    if not isinstance(raw, dict):
        raise ValueError("Expected a map of D-Bus properties")
    return {
        key: value.unpack() if isinstance(value, GLib.Variant) else value
        for key, value in raw.items()
    }


class SystemdClient:
    """Uses the system bus for PID 1 and session bus for systemd --user."""

    @staticmethod
    def _connect(
        scope: Scope,
        on_success: Callable[[Gio.DBusConnection], None],
        on_error: ErrorCallback,
    ) -> None:
        if scope not in ("system", "user"):
            on_error("Unsupported systemd manager scope")
            return
        bus_type = Gio.BusType.SYSTEM if scope == "system" else Gio.BusType.SESSION

        def ready(_source: object, result: Gio.AsyncResult, _data: object) -> None:
            try:
                on_success(Gio.bus_get_finish(result))
            except GLib.Error as exc:
                on_error(f"Could not connect to {scope} D-Bus: {exc.message}")

        Gio.bus_get(bus_type, None, ready, None)

    @staticmethod
    def _call(
        connection: Gio.DBusConnection,
        method: str,
        on_success: Callable[[GLib.Variant], None],
        on_error: ErrorCallback,
        *,
        path: str = MANAGER_PATH,
        interface: str = MANAGER_INTERFACE,
        parameters: GLib.Variant | None = None,
        flags: Gio.DBusCallFlags = Gio.DBusCallFlags.NONE,
    ) -> None:
        def completed(source: Gio.DBusConnection, result: Gio.AsyncResult, _data: object) -> None:
            try:
                on_success(source.call_finish(result))
            except GLib.Error as exc:
                on_error(f"systemd {method} failed: {exc.message}")
            except (ValueError, TypeError, IndexError, KeyError) as exc:
                on_error(f"Invalid systemd {method} response: {exc}")

        connection.call(
            BUS_NAME,
            path,
            interface,
            method,
            parameters,
            None,
            flags,
            TIMEOUT_MS,
            None,
            completed,
            None,
        )

    def fetch_services(
        self,
        scope: Scope,
        on_success: ListCallback,
        on_error: ErrorCallback,
    ) -> None:
        """Fetch loaded services and known unit-file states without blocking GTK."""
        def connected(connection: Gio.DBusConnection) -> None:
            def got_units(reply: GLib.Variant) -> None:
                rows = reply.unpack()[0]

                def got_files(files_reply: GLib.Variant) -> None:
                    on_success(normalize_services(rows, files_reply.unpack()[0], scope), None)

                def files_unavailable(message: str) -> None:
                    on_success(normalize_services(rows, [], scope), message)

                self._call(connection, "ListUnitFiles", got_files, files_unavailable)

            self._call(connection, "ListUnits", got_units, on_error)

        self._connect(scope, connected, on_error)

    def fetch_details(
        self,
        scope: Scope,
        name: str,
        on_success: DetailCallback,
        on_error: ErrorCallback,
    ) -> None:
        """Read authoritative Unit and Service properties on demand.

        GetUnit resolves the current object path, avoiding stale paths after
        service reloads. A missing Service interface is a partial result.
        """
        if not name.endswith(".service") or "/" in name or not name:
            on_error("Invalid service unit name")
            return

        def connected(connection: Gio.DBusConnection) -> None:
            def got_path(reply: GLib.Variant) -> None:
                path = reply.unpack()[0]
                if not isinstance(path, str) or not path.startswith(
                    "/org/freedesktop/systemd1/unit/"
                ):
                    on_error("systemd returned an unexpected unit object path")
                    return

                def got_unit(reply_unit: GLib.Variant) -> None:
                    unit_props = unpack_properties(reply_unit)

                    def got_service(reply_service: GLib.Variant) -> None:
                        on_success(
                            ServiceDetails(
                                scope=scope,
                                requested_name=name,
                                unit=unit_props,
                                service=unpack_properties(reply_service),
                            )
                        )

                    def service_unavailable(message: str) -> None:
                        on_success(
                            ServiceDetails(
                                scope=scope,
                                requested_name=name,
                                unit=unit_props,
                                service={},
                                service_warning=message,
                            )
                        )

                    self._call(
                        connection,
                        "GetAll",
                        got_service,
                        service_unavailable,
                        path=path,
                        interface=PROPERTIES_INTERFACE,
                        parameters=GLib.Variant("(s)", (SERVICE_INTERFACE,)),
                    )

                self._call(
                    connection,
                    "GetAll",
                    got_unit,
                    on_error,
                    path=path,
                    interface=PROPERTIES_INTERFACE,
                    parameters=GLib.Variant("(s)", (UNIT_INTERFACE,)),
                )

            self._call(
                connection,
                "GetUnit",
                got_path,
                on_error,
                parameters=GLib.Variant("(s)", (name,)),
            )

        self._connect(scope, connected, on_error)
