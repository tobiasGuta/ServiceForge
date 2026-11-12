"""Test counts without requiring a running desktop environment."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from serviceforge.models.overview import summarize_services  # noqa: E402
from serviceforge.models.service import ServiceRecord  # noqa: E402


def record(name, state):
    return ServiceRecord("system", name, "", "loaded", state, "dead", None)


class OverviewTests(unittest.TestCase):
    def test_all_categories_and_sorted_failures(self):
        summary = summarize_services([
            record("z.service", "failed"),
            record("active.service", "active"),
            record("a.service", "failed"),
            record("inactive.service", "inactive"),
            record("loading.service", "activating"),
        ])
        self.assertEqual(
            (summary.total, summary.active, summary.inactive, summary.failed, summary.other),
            (5, 1, 1, 2, 1),
        )
        self.assertEqual(
            [x.name for x in summary.failed_units],
            ["a.service", "z.service"],
        )

    def test_empty_snapshot(self):
        self.assertEqual(summarize_services([]).total, 0)


if __name__ == "__main__":
    unittest.main()
