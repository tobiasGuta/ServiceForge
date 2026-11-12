"""Fedora-only fake-D-Bus event watcher tests. Never touch the real manager."""

from unittest.mock import patch

from gi.repository import GLib

from serviceforge.backend import live_monitor
from serviceforge.backend.live_monitor import LiveMonitor
from serviceforge.backend.systemd_client import SystemdClient


class FakeConnection:
    def __init__(self):
        self.handlers = {}
        self.next_handler = 1
        self.unsubscribe_calls = 0

    def signal_subscribe(
        self, _sender, interface, member, path, _arg0, _flags, callback, _data,
    ):
        ident = self.next_handler
        self.next_handler += 1
        self.handlers[ident] = (interface, member, path, callback)
        return ident

    def signal_unsubscribe(self, ident):
        assert ident in self.handlers
        self.handlers.pop(ident)

    def call(self, _bus, _path, _iface, method, *_args):
        assert method == "Unsubscribe"
        self.unsubscribe_calls += 1

    def emit(self, interface, member, path, params):
        for expected_iface, expected_member, expected_path, callback in list(
            self.handlers.values()
        ):
            if interface == expected_iface and member == expected_member:
                if expected_path is None or expected_path == path:
                    callback(
                        self, "org.freedesktop.systemd1", path,
                        interface, member, params, None,
                    )


class FakeTimers:
    def __init__(self):
        self.next_id = 1
        self.scheduled = {}
        self.cancelled = []

    def schedule(self, interval, callback, *args):
        ident = self.next_id
        self.next_id += 1
        self.scheduled[ident] = (interval, callback, args)
        return ident

    def remove(self, ident):
        self.cancelled.append(ident)
        self.scheduled.pop(ident, None)

    def fire(self, ident):
        _interval, callback, args = self.scheduled.pop(ident)
        return callback(*args)


MANAGER = "org.freedesktop.systemd1.Manager"
PATH = "/org/freedesktop/systemd1"
PROPS = "org.freedesktop.DBus.Properties"
UNIT_PATH = PATH + "/unit/example_2eservice"


def exercise_monitor():
    connection = FakeConnection()
    timers = FakeTimers()
    events = []
    refreshes = []
    statuses = []

    def connect(scope, success, error):
        assert scope == "user"
        success(connection)

    def call(_connection, method, success, error, **kwargs):
        assert method == "Subscribe"
        success(None)

    with patch.object(SystemdClient, "_connect", side_effect=connect), patch.object(
        SystemdClient, "_call", side_effect=call
    ), patch.object(
        live_monitor.GLib, "timeout_add",
        side_effect=lambda milliseconds, cb, *args: timers.schedule(
            milliseconds, cb, *args,
        ),
    ), patch.object(
        live_monitor.GLib, "timeout_add_seconds",
        side_effect=lambda seconds, cb, *args: timers.schedule(
            seconds * 1000, cb, *args,
        ),
    ), patch.object(
        live_monitor.GLib, "source_remove", side_effect=timers.remove,
    ):
        monitor = LiveMonitor(
            lambda: refreshes.append(True),
            events.append, statuses.append,
        )
        monitor.start("user")
        assert len(connection.handlers) == 6
        assert "Live" in statuses[-1]

        connection.emit(
            MANAGER, "JobRemoved", PATH,
            GLib.Variant(
                "(uoss)",
                (31, PATH + "/job/31", "example.service", "done"),
            ),
        )
        connection.emit(
            PROPS, "PropertiesChanged", UNIT_PATH,
            GLib.Variant(
                "(sa{sv}as)",
                (
                    "org.freedesktop.systemd1.Unit",
                    {"ActiveState": GLib.Variant("s", "active")},
                    [],
                ),
            ),
        )
        connection.emit(
            MANAGER, "UnitFilesChanged", PATH,
            GLib.Variant("()", ()),
        )
        assert len(events) == 2, events
        assert events[0].unit == "example.service"
        # Three relevant events cause exactly one debounced refresh.
        bursts = [
            ident for ident, item in timers.scheduled.items()
            if item[0] == 750
        ]
        assert len(bursts) == 1
        timers.fire(bursts[0])
        assert len(refreshes) == 1
        assert all(item[0] != 750 for item in timers.scheduled.values())

        # Ignore timer units and manager reload beginning.
        connection.emit(
            MANAGER, "UnitNew", PATH,
            GLib.Variant("(so)", ("test.timer", UNIT_PATH)),
        )
        connection.emit(
            MANAGER, "Reloading", PATH, GLib.Variant("(b)", (True,)),
        )
        assert len(events) == 2
        # Periodic reconciliation should be very slow, never a busy loop.
        scheduled_periodic = [
            ident for ident, item in timers.scheduled.items()
            if item[0] == 90000
        ]
        assert len(scheduled_periodic) == 1

        stale_handler = list(connection.handlers.values())[0][3]
        monitor.stop()
        assert connection.handlers == {}
        assert connection.unsubscribe_calls == 1
        assert scheduled_periodic[0] in timers.cancelled

        stale_handler(
            connection, "org.freedesktop.systemd1", PATH, MANAGER,
            "UnitFilesChanged", GLib.Variant("()", ()), None,
        )
        assert len(events) == 2  # no callbacks after Stop
        assert len(refreshes) == 1


def exercise_subscription_failure():
    connection = FakeConnection()
    timers = FakeTimers()
    statuses = []
    refreshes = []

    def connect(scope, success, error):
        success(connection)

    def subscribe(_conn, method, success, error, **kwargs):
        error("subscriptions not supported")

    with patch.object(SystemdClient, "_connect", side_effect=connect), patch.object(
        SystemdClient, "_call", side_effect=subscribe
    ), patch.object(
        live_monitor.GLib, "timeout_add_seconds",
        side_effect=lambda seconds, cb, *args: timers.schedule(
            seconds * 1000, cb, *args,
        ),
    ), patch.object(
        live_monitor.GLib, "source_remove", side_effect=timers.remove,
    ):
        monitor = LiveMonitor(
            lambda: refreshes.append(True), lambda _: None, statuses.append,
        )
        monitor.start("system")
        assert not connection.handlers
        assert "Polling" in statuses[-1]
        fallback_id = next(iter(timers.scheduled))
        assert timers.scheduled[fallback_id][0] == 45000
        assert timers.fire(fallback_id) == GLib.SOURCE_CONTINUE
        assert len(refreshes) == 1
        monitor.stop()
        assert connection.unsubscribe_calls == 0


if __name__ == "__main__":
    exercise_monitor()
    exercise_subscription_failure()
    print("Fake systemd live monitoring and fallback checks passed")
