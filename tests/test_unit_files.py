"""Pure action policy tests: never contact systemd or change real units."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from serviceforge.models.service import ServiceRecord  # noqa: E402
from serviceforge.models.unit_files import (  # noqa: E402
    FileActionOutcome, file_action_allowed, file_action_message,
    requires_typed_confirmation,
)


def record(
    name="serviceforge-config-test.service",
    *, scope="user", state="disabled", active="inactive", file=True,
):
    return ServiceRecord(
        scope, name, "test unit", "loaded", active, "dead", state,
        unit_file_path=(
            f"/usr/lib/systemd/system/{name}"
            if scope == "system" else
            f"/home/test/.local/share/systemd/user/{name}"
        ) if file else None,
    )


class FilePolicyTests(unittest.TestCase):
    def test_disabled_can_enable_or_mask_only_when_inactive(self):
        unit = record()
        self.assertTrue(file_action_allowed(unit, "enable", "disabled", active_state="active"))
        self.assertTrue(file_action_allowed(unit, "mask", "disabled", active_state="inactive"))
        self.assertFalse(file_action_allowed(unit, "mask", "disabled", active_state="active"))
        self.assertFalse(file_action_allowed(unit, "disable", "disabled", active_state="inactive"))

    def test_enabled_can_only_disable_and_masked_can_only_unmask(self):
        enabled = record(state="enabled")
        self.assertTrue(file_action_allowed(enabled, "disable", "enabled"))
        self.assertFalse(file_action_allowed(enabled, "mask", "enabled", active_state="inactive"))
        masked = record(state="masked")
        self.assertTrue(file_action_allowed(masked, "unmask", "masked"))
        self.assertFalse(file_action_allowed(masked, "enable", "masked"))

    def test_special_file_states_are_not_mistaken_for_disabled(self):
        for state in ("static", "indirect", "generated", "alias", "enabled-runtime",
                      "masked-runtime", "linked", "bad"):
            for action in ("enable", "disable", "mask", "unmask"):
                self.assertFalse(file_action_allowed(
                    record(state=state), action, state, active_state="inactive"
                ))

    def test_missing_file_and_unsafe_system_units_are_blocked(self):
        self.assertFalse(file_action_allowed(
            record(file=False), "enable", "disabled"
        ))
        for name in ("systemd-journald.service", "NetworkManager.service",
                     "dbus-broker.service", "sshd.service"):
            self.assertFalse(file_action_allowed(
                record(name=name, scope="system"), "mask", "disabled",
                active_state="inactive",
            ))
            self.assertFalse(file_action_allowed(
                record(name=name, scope="system"), "enable", "disabled",
            ))

    def test_typed_name_and_user_facing_consequences(self):
        unit = record()
        self.assertTrue(requires_typed_confirmation(unit, "mask"))
        self.assertFalse(requires_typed_confirmation(unit, "enable"))
        self.assertTrue(requires_typed_confirmation(
            record(scope="system"), "enable"
        ))
        message = file_action_message("disable", unit)
        self.assertIn("does not stop", message.lower())
        self.assertIn("persists across reboots", message)

    def test_verification_is_not_inferred_from_successful_method_return(self):
        def outcome(action, state):
            return FileActionOutcome(action, "x.service", "disabled", state, (), None)
        self.assertTrue(outcome("enable", "enabled").verified)
        self.assertFalse(outcome("enable", "disabled").verified)
        self.assertTrue(outcome("unmask", "disabled").verified)
        self.assertFalse(outcome("unmask", "masked").verified)
        self.assertFalse(outcome("unmask", "not-found").verified)


if __name__ == "__main__":
    unittest.main()
