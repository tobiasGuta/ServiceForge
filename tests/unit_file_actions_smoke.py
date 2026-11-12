"""Fedora-only mocked D-Bus verification of unit-file writes and Polkit flags.

No actual systemd call is made; all calls are intercepted by patch.object.
"""

from unittest.mock import patch

from gi.repository import Gio, GLib

from serviceforge.backend.systemd_client import SystemdClient
from serviceforge.backend.unit_file_actions import (
    UnitFileActions, parameters_for_file_action,
)
from serviceforge.models.service import ServiceRecord


NAME = "serviceforge-config-test.service"


def record(*, state="disabled", active="inactive", scope="user"):
    return ServiceRecord(
        scope, NAME, "Disposable test", "loaded", active, "dead", state,
        unit_file_path=(
            "/etc/systemd/system/" + NAME if scope == "system"
            else "/home/test/.local/share/systemd/user/" + NAME
        ),
    )


def verify_signatures():
    for action, expected_type, expected_value in (
        ("enable", "(asbb)", ([NAME], False, False)),
        ("disable", "(asb)", ([NAME], False)),
        ("mask", "(asbb)", ([NAME], False, False)),
        ("unmask", "(asb)", ([NAME], False)),
    ):
        variant = parameters_for_file_action(action, NAME)
        assert variant.get_type_string() == expected_type
        assert variant.unpack() == expected_value


def exercise(action, old_state, new_state, *, change_state=True, deny=False, scope="user"):
    actor = UnitFileActions()
    observed = [old_state, new_state]
    errors, outcomes, calls = [], [], []

    def fake_get(scope, name, success, failure):
        assert scope in ("user", "system") and name == NAME
        success(observed.pop(0))

    def fake_connect(manager_scope, success, failure):
        assert manager_scope == scope
        success(object())

    def fake_call(_conn, method, success, failure, **kwargs):
        calls.append(method)
        assert method == {
            "enable": "EnableUnitFiles", "disable": "DisableUnitFiles",
            "mask": "MaskUnitFiles", "unmask": "UnmaskUnitFiles",
        }[action]
        assert kwargs["flags"] == Gio.DBusCallFlags.ALLOW_INTERACTIVE_AUTHORIZATION
        assert kwargs["timeout_ms"] == 180000
        assert kwargs["parameters"].get_type_string() in ("(asbb)", "(asb)")
        if deny:
            failure("GDBus.Error:org.freedesktop.PolicyKit1.Error.NotAuthorized")
        else:
            changes = [("symlink", "/tmp/test-link", "/tmp/test-target")]
            if action == "enable":
                success(GLib.Variant("(ba(sss))", (True, changes)))
            else:
                success(GLib.Variant("(a(sss))", (changes,)))

    with patch.object(actor, "get_state", side_effect=fake_get), patch.object(
        SystemdClient, "_connect", side_effect=fake_connect
    ), patch.object(SystemdClient, "_call", side_effect=fake_call):
        actor.execute(
            record(state=old_state, scope=scope), action, old_state,
            "inactive", outcomes.append, errors.append,
        )

    if change_state:
        assert calls == [fake_method(action)], calls
    else:
        assert calls == [], calls
    assert actor._in_progress is False
    if deny:
        assert not outcomes
        assert len(errors) == 1 and "NotAuthorized" in errors[0]
    else:
        assert not errors, errors
        assert len(outcomes) == 1
        assert outcomes[0].current_state == new_state
        assert outcomes[0].verified == (
            (action == "unmask" and new_state not in ("masked", "masked-runtime"))
            or (action != "unmask" and new_state == {
                "enable": "enabled", "disable": "disabled", "mask": "masked",
            }[action])
        )


def fake_method(action):
    return {
        "enable": "EnableUnitFiles", "disable": "DisableUnitFiles",
        "mask": "MaskUnitFiles", "unmask": "UnmaskUnitFiles",
    }[action]


def changed_before_write():
    actor = UnitFileActions()
    errors, calls = [], []

    def fake_get(scope, name, success, failure):
        success("enabled")  # User confirmed "disabled" but state changed.

    def fake_connect(scope, success, failure):
        success(object())

    def fake_call(_conn, method, success, failure, **kwargs):
        calls.append(method)
        raise AssertionError("No write may be issued on a stale state")

    with patch.object(actor, "get_state", side_effect=fake_get), patch.object(
        SystemdClient, "_connect", side_effect=fake_connect
    ), patch.object(SystemdClient, "_call", side_effect=fake_call):
        actor.execute(
            record(), "enable", "disabled", "inactive",
            lambda _: None, errors.append,
        )
    assert not calls
    assert len(errors) == 1 and "changed" in errors[0].lower()


if __name__ == "__main__":
    verify_signatures()
    exercise("enable", "disabled", "enabled")
    exercise("disable", "enabled", "disabled")
    exercise("mask", "disabled", "masked")
    exercise("unmask", "masked", "disabled")
    exercise("enable", "disabled", "disabled")  # Postflight mismatch.
    exercise("enable", "disabled", "enabled", deny=True)
    # System-manager request: simulate Polkit refusal without changing a unit.
    exercise(
        "enable", "disabled", "enabled",
        deny=True, scope="system",
    )
    changed_before_write()
    print("Mocked unit-file signatures, authorization and state checks passed")
