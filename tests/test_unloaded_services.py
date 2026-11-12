"""Regression for unloaded user services after a successful Stop job."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from serviceforge.backend.normalize import normalize_services  # noqa: E402
from serviceforge.models.overview import summarize_services  # noqa: E402


UNIT_PATH = "/home/example/.config/systemd/user/serviceforge-test.service"


def row(name, state="active"):
    return (name, "Disposable test service", "loaded", state, "running",
            "", "/org/freedesktop/systemd1/unit/test_2eservice", 0, "", "/")


class UnloadedServiceTests(unittest.TestCase):
    def test_stop_then_unload_remains_discoverable(self):
        before = normalize_services(
            [row("serviceforge-test.service")],
            [(UNIT_PATH, "static")],
            "user",
        )
        self.assertEqual(len(before), 1)
        self.assertTrue(before[0].loaded)
        self.assertEqual(before[0].active_state, "active")

        # systemd garbage-collects the unit after Stop, while the file remains.
        after = normalize_services([], [(UNIT_PATH, "static")], "user")
        self.assertEqual(len(after), 1)
        self.assertEqual(after[0].name, "serviceforge-test.service")
        self.assertFalse(after[0].loaded)
        self.assertEqual(after[0].unit_file_path, UNIT_PATH)
        self.assertEqual(after[0].load_state, "unloaded")
        self.assertEqual(after[0].active_state, "unknown")
        self.assertEqual(after[0].unit_file_state, "static")
        self.assertEqual(summarize_services(after).total, 0)

    def test_no_installed_file_after_cleanup_means_no_service(self):
        self.assertEqual(normalize_services([], [], "user"), [])

    def test_loaded_and_unloaded_do_not_duplicate(self):
        result = normalize_services(
            [row("foo.service"), row("bar.service", "failed")],
            [
                ("/usr/lib/systemd/system/foo.service", "enabled"),
                ("/usr/lib/systemd/system/extra.service", "disabled"),
                ("/usr/lib/systemd/system/only@.service", "static"),
            ],
            "system",
        )
        self.assertEqual(
            [entry.name for entry in result],
            ["bar.service", "extra.service", "foo.service"],
        )
        snapshot = summarize_services(result)
        self.assertEqual((snapshot.total, snapshot.failed, snapshot.other), (2, 1, 0))

    def test_invalid_file_row_fails_fast(self):
        with self.assertRaises(ValueError):
            normalize_services([], [("broken",)], "user")


if __name__ == "__main__":
    unittest.main()
