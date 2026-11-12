"""Fake journal Reader tests: no journal access or GTK required."""

from datetime import datetime, timezone
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from serviceforge.backend.journal_reader import read_journal  # noqa: E402
from serviceforge.models.journal import (  # noqa: E402
    JournalEntry,
    filter_entries,
    format_entries,
    normalize_entry,
)


class FakeReader:
    def __init__(self):
        self.matches = []
        self.seen_boot = False
        self.seen_tail = False
        self.closed = False
        self.rows = [
            {"MESSAGE": "new entry", "PRIORITY": "3"},
            {"MESSAGE": "old entry", "PRIORITY": "6"},
        ]

    def this_boot(self):
        self.seen_boot = True

    def add_match(self, **fields):
        self.matches.append(fields)

    def seek_tail(self):
        self.seen_tail = True

    def get_previous(self):
        return self.rows.pop(0) if self.rows else None

    def close(self):
        self.closed = True


class JournalTests(unittest.TestCase):
    def test_system_match_and_order(self):
        reader = FakeReader()
        entries = read_journal("system", "sshd.service", reader_factory=lambda: reader)
        self.assertEqual(reader.matches, [{"_SYSTEMD_UNIT": "sshd.service"}])
        self.assertTrue(reader.seen_boot and reader.seen_tail and reader.closed)
        self.assertEqual([e.message for e in entries], ["old entry", "new entry"])

    def test_user_match_includes_uid(self):
        reader = FakeReader()
        read_journal("user", "example.service", reader_factory=lambda: reader, uid=1001)
        self.assertEqual(reader.matches, [
            {"_SYSTEMD_USER_UNIT": "example.service"},
            {"_UID": "1001"},
        ])

    def test_invalid_names_never_open_reader(self):
        for unit in ("../x.service", "name\n.service", "x.timer"):
            with self.assertRaises(ValueError):
                read_journal("system", unit, reader_factory=lambda: self.fail("must not open"))

    def test_filters_severity_and_search(self):
        rows = [
            JournalEntry("now", 3, "connection failed"),
            JournalEntry("later", 6, "started"),
            JournalEntry("later", None, "unknown"),
        ]
        self.assertEqual([e.message for e in filter_entries(rows, max_priority=4)],
                         ["connection failed"])
        self.assertEqual([e.message for e in filter_entries(rows, search="START")],
                         ["started"])
        self.assertIn("[Error]", format_entries(rows))

    def test_missing_fields_and_long_messages(self):
        entry = normalize_entry({
            "MESSAGE": b"bad\xff",
            "PRIORITY": 9,
            "__REALTIME_TIMESTAMP": datetime(2026, 11, 11, tzinfo=timezone.utc),
        })
        self.assertIn("bad", entry.message)
        self.assertIsNone(entry.priority)
        self.assertNotEqual(entry.timestamp, "Time unknown")


if __name__ == "__main__":
    unittest.main()
