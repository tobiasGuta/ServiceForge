"""Unit tests that do not need a running desktop or Gio installation."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from serviceforge.backend.normalize import normalize_services  # noqa: E402


def unit(name, active="active", sub="running"):
    return (
        name, f"Description for {name}", "loaded", active, sub,
        "", "/org/freedesktop/systemd1/unit/example_2eservice",
        0, "", "/",
    )


class NormalizeServicesTests(unittest.TestCase):
    def test_runtime_state_does_not_imply_enablement(self):
        result = normalize_services(
            [unit("demo.service")],
            [("/usr/lib/systemd/system/demo.service", "disabled")],
            "system",
        )
        self.assertEqual(result[0].active_state, "active")
        self.assertEqual(result[0].unit_file_state, "disabled")

    def test_unmatched_file_is_unknown_not_disabled(self):
        result = normalize_services([unit("transient.service")], [], "system")
        self.assertIsNone(result[0].unit_file_state)
        self.assertEqual(result[0].startup_display, "Unknown")

    def test_filters_non_service_units_and_sorts(self):
        result = normalize_services(
            [unit("z.service"), unit("x.timer"), unit("a.service")],
            [], "user",
        )
        self.assertEqual([item.name for item in result], ["a.service", "z.service"])
        self.assertTrue(all(item.scope == "user" for item in result))

    def test_states_are_preserved_verbatim(self):
        result = normalize_services(
            [unit("demo.service", active="failed", sub="failed")],
            [("/run/systemd/system/demo.service", "masked-runtime")],
            "system",
        )
        self.assertEqual(result[0].active_state, "failed")
        self.assertEqual(result[0].unit_file_state, "masked-runtime")

    def test_rejects_bad_rows_and_unknown_scopes(self):
        with self.assertRaises(ValueError):
            normalize_services([("broken.service",)], [], "system")
        with self.assertRaises(ValueError):
            normalize_services([], [], "unknown")


if __name__ == "__main__":
    unittest.main()
