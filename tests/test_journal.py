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
        self.disjunctions = 0
        self.boot_id = None
        self.operations = []
        self.seen_tail = False
        self.closed = False
        self.rows = [
            {"MESSAGE": "new entry", "PRIORITY": "3"},
            {"MESSAGE": "old entry", "PRIORITY": "6"},
        ]

    def this_boot(self, boot_id=None):
        self.boot_id = boot_id
        self.operations.append("boot")

    def add_match(self, **fields):
        self.matches.append(fields)
        self.operations.append("match")

    def add_disjunction(self):
        self.disjunctions += 1
        self.operations.append("or")

    def add_conjunction(self):
        self.operations.append("and")

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
        self.assertEqual(reader.matches, [
            {"_SYSTEMD_UNIT": "sshd.service"},
            {"UNIT": "sshd.service", "_PID": "1"},
            {"OBJECT_SYSTEMD_UNIT": "sshd.service", "_UID": "0"},
        ])
        self.assertEqual(reader.disjunctions, 2)
        self.assertTrue(reader.seen_tail and reader.closed)
        self.assertEqual(reader.operations, ["boot", "and", "match", "or", "match", "or", "match"])
        self.assertEqual([e.message for e in entries], ["old entry", "new entry"])

    def test_user_match_includes_uid(self):
        reader = FakeReader()
        previous_boot = "a" * 32
        read_journal(
            "user", "example.service", reader_factory=lambda: reader, uid=1001,
            boot_id=previous_boot,
        )
        self.assertEqual(reader.matches, [
            {"_SYSTEMD_USER_UNIT": "example.service", "_UID": "1001"},
            {"USER_UNIT": "example.service", "_UID": "1001"},
        ])
        self.assertEqual(reader.disjunctions, 1)
        self.assertEqual(reader.boot_id, previous_boot)
        self.assertEqual(reader.operations, ["boot", "and", "match", "or", "match"])

    def test_failure_preview_filters_before_limiting_rows(self):
        reader = FakeReader()
        read_journal("system", "example.service", reader_factory=lambda: reader, max_priority=3)
        self.assertEqual(reader.operations[-5:], ["and", "match", "match", "match", "match"])
        self.assertEqual(reader.matches[-4:], [{"PRIORITY": str(i)} for i in range(4)])

    def test_invalid_names_never_open_reader(self):
        for unit in ("../x.service", "name\n.service", "x.timer"):
            with self.assertRaises(ValueError):
                read_journal("system", unit, reader_factory=lambda: self.fail("must not open"))

    def test_reader_closes_after_failure(self):
        class BrokenReader(FakeReader):
            def get_previous(self):
                raise PermissionError("not allowed")
        reader = BrokenReader()
        with self.assertRaises(PermissionError):
            read_journal("system", "demo.service", reader_factory=lambda: reader)
        self.assertTrue(reader.closed)

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
