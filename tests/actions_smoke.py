"""Fedora-only D-Bus job-tracking smoke tests with no real service changes."""

from unittest.mock import patch

from gi.repository import Gio, GLib

from serviceforge.backend.service_actions import ServiceActions
from serviceforge.backend.systemd_client import SystemdClient


JOB = "/org/freedesktop/systemd1/job/27"
UNIT = "serviceforge-test.service"


class FakeReply:
    def __init__(self, path):
        self.path = path

    def unpack(self):
        return (self.path,)


class FakeConnection:
    def __init__(self):
        self.listener = None
        self.unsubscribe_count = 0
        self.unsubscribed_manager = 0

    def signal_subscribe(self, _sender, _iface, _signal, _path, _arg0, _flags, callback, _data):
        self.listener = callback
        return 23

    def signal_unsubscribe(self, ident):
        assert ident == 23
        self.unsubscribe_count += 1
        self.listener = None

    def call(self, _bus, _path, _iface, method, *_rest):
        assert method == "Unsubscribe"
        self.unsubscribed_manager += 1

    def emit(self, result):
        assert self.listener is not None
        self.listener(
            self, "org.freedesktop.systemd1",
            "/org/freedesktop/systemd1",
            "org.freedesktop.systemd1.Manager",
            "JobRemoved",
            GLib.Variant("(uoss)", (27, JOB, UNIT, result)),
            None,
        )


def exercise(early: bool, result: str):
    connection = FakeConnection()
    successes = []
    errors = []
    saw_auth_flag = []
    calls = []

    def fake_connect(scope, on_success, on_error):
        assert scope == "user"
        on_success(connection)

    def fake_call(conn, method, on_success, on_error, **kwargs):
        calls.append(method)
        if method == "Subscribe":
            on_success(None)
        elif method == "RestartUnit":
            assert kwargs["parameters"].unpack() == (UNIT, "replace")
            saw_auth_flag.append(
                kwargs.get("flags") == Gio.DBusCallFlags.ALLOW_INTERACTIVE_AUTHORIZATION
                and kwargs.get("timeout_ms") == 180000
            )
            if early:
                conn.emit(result)
            on_success(FakeReply(JOB))
            if not early:
                conn.emit(result)
        else:
            raise AssertionError(f"Unexpected method: {method}")

    with patch.object(SystemdClient, "_connect", side_effect=fake_connect), patch.object(
        SystemdClient, "_call", side_effect=fake_call
    ):
        actor = ServiceActions()
        actor.execute("user", UNIT, "restart", successes.append, errors.append)

    assert not errors, errors
    assert len(successes) == 1
    assert successes[0].result == result
    assert successes[0].succeeded is (result == "done")
    assert saw_auth_flag == [True]
    assert calls == ["Subscribe", "RestartUnit"]
    assert connection.unsubscribe_count == 1
    assert connection.unsubscribed_manager == 1


def verify_rejections():
    connection_attempts = []

    def fake_connect(*args):
        connection_attempts.append(args)

    with patch.object(SystemdClient, "_connect", side_effect=fake_connect):
        actor = ServiceActions()
        errors = []
        actor.execute("user", "../../bad.service", "restart", lambda _: None, errors.append)
        actor.execute("user", UNIT, "delete", lambda _: None, errors.append)
        assert len(errors) == 2
        assert not connection_attempts


if __name__ == "__main__":
    exercise(early=True, result="done")
    exercise(early=False, result="failed")
    verify_rejections()
    print("Mocked systemd job tracking and authorization flags passed")
