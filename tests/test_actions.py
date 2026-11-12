"""Policy tests: no real D-Bus writes or elevated access."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from serviceforge.models.actions import (  # noqa: E402
    ActionOutcome, allowed_actions, confirmation_text, validate_unit,
)
from serviceforge.models.service import ServiceRecord  # noqa: E402


def service(name="example.service", active="active", load="loaded", startup="enabled"):
    return ServiceRecord("system", name, "", load, active, "running", startup)


class RuntimeActionPolicyTests(unittest.TestCase):
    def test_only_whitelisted_names_are_allowed(self):
        self.assertTrue(validate_unit("foo@bar.service"))
        for name in ("../bad.service", "x.service\n", "bad.timer", "", "/etc/passwd"):
            self.assertFalse(validate_unit(name))

    def test_active_service_allows_stop_restart_not_start(self):
        self.assertEqual(allowed_actions(service()), set())
        self.assertEqual(
            allowed_actions(service(), can_start=True, can_stop=True),
            {"stop", "restart"},
        )
        self.assertEqual(
            allowed_actions(
                service(), can_start=True, can_stop=True, can_reload=True
            ),
            {"stop", "restart", "reload"},
        )

    def test_inactive_or_failed_allows_only_start(self):
        self.assertEqual(
            allowed_actions(service(active="inactive"), can_start=True), {"start"}
        )
        self.assertEqual(
            allowed_actions(service(active="failed"), can_start=True), {"start"}
        )

    def test_no_actions_for_missing_masked_or_transitioning(self):
        self.assertEqual(allowed_actions(service(load="not-found")), set())
        self.assertEqual(allowed_actions(service(startup="masked")), set())
        self.assertEqual(allowed_actions(service(active="activating")), set())

    def test_manual_refusal_and_capabilities_are_respected(self):
        self.assertEqual(
            allowed_actions(
                service(), can_start=True, can_stop=True,
                refuse_manual_stop=True,
            ),
            set(),
        )
        self.assertEqual(
            allowed_actions(
                service(), can_start=False, can_stop=True,
            ),
            {"stop"},
        )
        self.assertEqual(
            allowed_actions(
                service(active="inactive"), can_start=True,
                refuse_manual_start=True,
            ),
            set(),
        )

    def test_high_impact_warning_and_runtime_scope(self):
        text = confirmation_text("restart", service(name="NetworkManager.service"))
        self.assertIn("High-impact", text)
        self.assertIn("runtime state", text)
        self.assertIn("Polkit", text)

    def test_queued_not_success(self):
        self.assertFalse(ActionOutcome("restart", "foo.service", "queued").succeeded)
        self.assertTrue(ActionOutcome("restart", "foo.service", "done").succeeded)
        self.assertFalse(ActionOutcome("restart", "foo.service", "failed").succeeded)


if __name__ == "__main__":
    unittest.main()
