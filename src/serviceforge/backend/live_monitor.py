"""Event-driven systemd monitoring with debouncing and slow polling fallback.

This client is read-only apart from Manager.Subscribe/Unsubscribe, which
register notifications. No privileged manager actions are issued.
"""

from collections.abc import Callable
from datetime import datetime

import gi
gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from serviceforge.backend.systemd_client import (
    BUS_NAME, MANAGER_INTERFACE, MANAGER_PATH, SystemdClient,
)
from serviceforge.models.monitoring import (
    ActivityEvent, describe_manager_signal, should_refresh_for_signal,
)
from serviceforge.models.service import Scope


REFRESH_DEBOUNCE_MS = 750
RECONCILE_SECONDS = 90
FALLBACK_SECONDS = 45

RefreshCallback = Callable[[], None]
EventCallback = Callable[[ActivityEvent], None]
StatusCallback = Callable[[str], None]


class LiveMonitor:
    """Observe one selected manager at a time, on the GTK/GLib main context."""

    def __init__(
        self,
        on_refresh: RefreshCallback,
        on_event: EventCallback,
        on_status: StatusCallback,
    ) -> None:
        self._on_refresh = on_refresh
        self._on_event = on_event
        self._on_status = on_status
        self._generation = 0
        self._active = False
        self._scope: Scope | None = None
        self._connection: Gio.DBusConnection | None = None
        self._subscriptions: list[int] = []
        self._subscribed_manager = False
        self._refresh_source: int | None = None
        self._reconcile_source: int | None = None

    def start(self, scope: Scope) -> None:
        if scope not in ("system", "user"):
            raise ValueError("Unknown systemd manager")
        self.stop()
        self._active = True
        self._scope = scope
        generation = self._generation
        self._on_status(f"Connecting to {scope} manager events…")

        def connected(connection: Gio.DBusConnection) -> None:
            if not self._is_current(generation):
                return
            self._connection = connection

            for interface, member, path in (
                (MANAGER_INTERFACE, "UnitNew", MANAGER_PATH),
                (MANAGER_INTERFACE, "UnitRemoved", MANAGER_PATH),
                (MANAGER_INTERFACE, "JobRemoved", MANAGER_PATH),
                (MANAGER_INTERFACE, "UnitFilesChanged", MANAGER_PATH),
                (MANAGER_INTERFACE, "Reloading", MANAGER_PATH),
                ("org.freedesktop.DBus.Properties", "PropertiesChanged", None),
            ):
                ident = connection.signal_subscribe(
                    BUS_NAME, interface, member, path, None,
                    Gio.DBusSignalFlags.NONE,
                    lambda _conn, _sender, object_path, iface, signal, params, _data:
                        self._signal_received(
                            generation, object_path, iface, signal, params,
                        ),
                    None,
                )
                self._subscriptions.append(ident)

            SystemdClient._call(
                connection,
                "Subscribe",
                lambda _reply: self._subscription_ready(generation),
                lambda message: self._subscription_failed(generation, message),
            )

        def failed(message: str) -> None:
            if self._is_current(generation):
                self._start_fallback(generation, message)

        SystemdClient._connect(scope, connected, failed)

    def stop(self) -> None:
        self._generation += 1
        self._active = False
        self._scope = None
        for source in (self._refresh_source, self._reconcile_source):
            if source is not None:
                GLib.source_remove(source)
        self._refresh_source = None
        self._reconcile_source = None
        self._remove_subscriptions()
        self._on_status("Live monitoring paused · manual refresh available")

    def _remove_subscriptions(self) -> None:
        connection = self._connection
        if connection is None:
            return
        for ident in self._subscriptions:
            connection.signal_unsubscribe(ident)
        self._subscriptions.clear()
        if self._subscribed_manager:
            connection.call(
                BUS_NAME, MANAGER_PATH, MANAGER_INTERFACE, "Unsubscribe",
                None, None, Gio.DBusCallFlags.NONE,
                5000, None, None, None,
            )
            self._subscribed_manager = False
        self._connection = None

    def _is_current(self, generation: int) -> bool:
        return self._active and generation == self._generation

    def _subscription_ready(self, generation: int) -> None:
        if not self._is_current(generation):
            return
        self._subscribed_manager = True
        self._on_status(
            "Live · systemd events · automatic reconciliation every 90 seconds"
        )
        self._reconcile_source = GLib.timeout_add_seconds(
            RECONCILE_SECONDS, self._periodic_reconcile, generation,
        )

    def _subscription_failed(self, generation: int, message: str) -> None:
        if not self._is_current(generation):
            return
        self._remove_subscriptions()
        self._start_fallback(generation, message)

    def _start_fallback(self, generation: int, message: str) -> None:
        if not self._is_current(generation):
            return
        self._on_status(
            f"Polling every {FALLBACK_SECONDS} seconds "
            f"(live signals unavailable: {message})"
        )
        if self._reconcile_source is not None:
            GLib.source_remove(self._reconcile_source)
        self._reconcile_source = GLib.timeout_add_seconds(
            FALLBACK_SECONDS, self._periodic_reconcile, generation,
        )

    def _periodic_reconcile(self, generation: int) -> bool:
        if not self._is_current(generation):
            return GLib.SOURCE_REMOVE
        self._on_refresh()
        return GLib.SOURCE_CONTINUE

    def _signal_received(
        self, generation: int, path: str, interface: str, signal: str,
        parameters: GLib.Variant,
    ) -> None:
        if not self._is_current(generation):
            return
        try:
            values = parameters.unpack()
        except (ValueError, TypeError):
            return
        if not isinstance(values, (tuple, list)):
            return
        if not should_refresh_for_signal(interface, signal, path, values):
            return

        if interface == MANAGER_INTERFACE and self._scope is not None:
            event = describe_manager_signal(
                self._scope, signal, values,
                datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            )
            if event is not None:
                self._on_event(event)
        self._schedule_refresh(generation)

    def _schedule_refresh(self, generation: int) -> None:
        if self._refresh_source is not None:
            return

        def finished() -> bool:
            self._refresh_source = None
            if self._is_current(generation):
                self._on_refresh()
            return GLib.SOURCE_REMOVE

        self._refresh_source = GLib.timeout_add(
            REFRESH_DEBOUNCE_MS, finished,
        )
