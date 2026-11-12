"""Activity history and systemd signal relevance without GTK or systemd."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from serviceforge.models.monitoring import (  # noqa: E402
    ActivityEvent, ActivityFeed, describe_manager_signal,
    should_refresh_for_signal,
)


MANAGER = "org.freedesktop.systemd1.Manager"
PROPS = "org.freedesktop.DBus.Properties"
UNIT_PATH = "/org/freedesktop/systemd1/unit/example_2eservice"


class ActivityTests(unittest.TestCase):
    def test_recent_events_are_bounded_and_newest_first(self):
        feed = ActivityFeed(2)
        for idx in range(3):
            feed.add(ActivityEvent("system", f"time-{idx}", "Job finished", "done"))
        self.assertEqual(
            [item.when for item in feed.recent()],
            ["time-2", "time-1"],
        )

    def test_reports_jobs_but_does_not_claim_service_started(self):
        event = describe_manager_signal(
            "user", "JobRemoved",
            (17, "/org/freedesktop/systemd1/job/17", "example.service", "done"),
            "12:45:00",
        )
        self.assertEqual(event.unit, "example.service")
        self.assertEqual(event.detail, "Result: done")
        self.assertEqual(event.title, "Job finished")

    def test_load_unload_not_confused_with_installed_unit_files(self):
        event = describe_manager_signal(
            "system", "UnitRemoved", ("example.service", UNIT_PATH), "now"
        )
        self.assertIn("In-memory", event.detail)
        self.assertIsNone(describe_manager_signal(
            "system", "UnitNew", ("example.timer", UNIT_PATH), "now",
        ))

    def test_file_changes_and_reload_complete(self):
        self.assertEqual(
            describe_manager_signal("system", "UnitFilesChanged", (), "t").title,
            "Unit files changed",
        )
        self.assertIsNone(
            describe_manager_signal("system", "Reloading", (True,), "t"),
        )
        self.assertEqual(
            describe_manager_signal("system", "Reloading", (False,), "t").title,
            "Manager reloaded",
        )

    def test_only_relevant_properties_trigger_refresh(self):
        self.assertTrue(should_refresh_for_signal(
            PROPS, "PropertiesChanged", UNIT_PATH,
            ("org.freedesktop.systemd1.Unit", {"ActiveState": "failed"}, []),
        ))
        self.assertFalse(should_refresh_for_signal(
            PROPS, "PropertiesChanged", UNIT_PATH,
            ("org.freedesktop.systemd1.Unit", {"Description": "text"}, []),
        ))
        self.assertFalse(should_refresh_for_signal(
            PROPS, "PropertiesChanged", "/org/freedesktop/systemd1",
            ("org.freedesktop.systemd1.Unit", {"ActiveState": "failed"}, []),
        ))
        self.assertTrue(should_refresh_for_signal(
            MANAGER, "JobRemoved", "/org/freedesktop/systemd1",
            (1, "/", "test.service", "done"),
        ))
        self.assertFalse(should_refresh_for_signal(
            MANAGER, "Reloading", "/org/freedesktop/systemd1", (True,),
        ))

    def test_unknown_data_is_ignored(self):
        self.assertIsNone(describe_manager_signal("user", "JobRemoved", (), "t"))
        with self.assertRaises(ValueError):
            ActivityFeed(0)


if __name__ == "__main__":
    unittest.main()
