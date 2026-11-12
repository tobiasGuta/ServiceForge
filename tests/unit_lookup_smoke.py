"""Mocked Fedora smoke test: inspecting a stopped and unloaded service."""
from unittest.mock import patch
from gi.repository import GLib
from serviceforge.backend.systemd_client import SystemdClient

UNIT = "serviceforge-test.service"
PATH = "/org/freedesktop/systemd1/unit/serviceforge_2dtest_2eservice"

def test_found():
    calls, successes, errors = [], [], []
    def connected(scope, callback, on_error):
        assert scope == "user"
        callback(object())
    def call(_conn, method, success, error, **kwargs):
        calls.append(method)
        if method == "LoadUnit":
            assert kwargs["parameters"].unpack() == (UNIT,)
            success(GLib.Variant("(o)", (PATH,)))
        elif method == "GetAll":
            interface = kwargs["parameters"].unpack()[0]
            if interface == "org.freedesktop.systemd1.Unit":
                props = {"Id": GLib.Variant("s", UNIT),
                         "LoadState": GLib.Variant("s", "loaded"),
                         "ActiveState": GLib.Variant("s", "inactive"),
                         "CanStart": GLib.Variant("b", True)}
            else:
                props = {"Type": GLib.Variant("s", "simple")}
            success(GLib.Variant("(a{sv})", (props,)))
        else:
            raise AssertionError(method)
    with patch.object(SystemdClient, "_connect", side_effect=connected), patch.object(
        SystemdClient, "_call", side_effect=call
    ):
        SystemdClient().fetch_details(
            "user", UNIT, successes.append, errors.append, known_unit_file=True
        )
    assert not errors, errors
    assert len(successes) == 1
    assert successes[0].unit["ActiveState"] == "inactive"
    assert successes[0].unit["CanStart"] is True
    assert calls == ["LoadUnit", "GetAll", "GetAll"], calls

def test_deleted_file():
    calls, errors = [], []
    def connected(scope, callback, error):
        callback(object())
    def call(_conn, method, success, error, **kwargs):
        calls.append(method)
        assert method == "LoadUnit"
        error("GDBus.Error:org.freedesktop.systemd1.NoSuchUnit")
    with patch.object(SystemdClient, "_connect", side_effect=connected), patch.object(
        SystemdClient, "_call", side_effect=call
    ):
        SystemdClient().fetch_details(
            "user", UNIT, lambda _: None, errors.append, known_unit_file=True
        )
    assert calls == ["LoadUnit"], calls
    assert len(errors) == 1 and "Refresh" in errors[0]

def test_transient_unloaded():
    calls, errors = [], []
    def connected(scope, callback, error):
        callback(object())
    def call(_conn, method, success, error, **kwargs):
        calls.append(method)
        assert method == "GetUnit"
        error("GDBus.Error:org.freedesktop.systemd1.NoSuchUnit")
    with patch.object(SystemdClient, "_connect", side_effect=connected), patch.object(
        SystemdClient, "_call", side_effect=call
    ):
        SystemdClient().fetch_details(
            "user", "temporary.service", lambda _: None, errors.append,
            known_unit_file=False,
        )
    assert calls == ["GetUnit"]
    assert len(errors) == 1 and "no longer loaded" in errors[0].lower()

if __name__ == "__main__":
    test_found()
    test_deleted_file()
    test_transient_unloaded()
    print("Unloaded unit inspection mock checks passed")
