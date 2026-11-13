"""Run the native journal reader against a two-boot journal export fixture."""

from os import getuid
from pathlib import Path
from subprocess import run
from tempfile import TemporaryDirectory

from systemd import id128, journal

from serviceforge.backend.journal_reader import read_journal


def main() -> None:
    current = id128.get_boot().hex
    previous = id128.randomize().hex
    unit = "example.service"
    with TemporaryDirectory() as directory:
        path = Path(directory)
        rows = (
            (previous, 1, "Previous boot unit message", "_SYSTEMD_UNIT", "3"),
            (previous, 2, "Previous boot manager message", "UNIT", "3"),
            (current, 3, "Current boot manager message", "UNIT", "3"),
            (current, 4, "Current boot informational message", "_SYSTEMD_UNIT", "6"),
            (previous, 5, "Previous boot user manager message", "USER_UNIT", "3"),
            (current, 6, "Current boot user manager message", "USER_UNIT", "3"),
            (current, 7, "Current boot user service message", "_SYSTEMD_USER_UNIT", "6"),
        )
        export = "".join(
            f"__REALTIME_TIMESTAMP={1700000000000000 + timestamp}\n"
            f"__MONOTONIC_TIMESTAMP={timestamp}\n"
            f"_BOOT_ID={boot}\n_PID=1\n_UID={getuid()}\nPRIORITY={priority}\n"
            f"{field}={unit}\nMESSAGE={message}\n\n"
            for boot, timestamp, message, field, priority in rows
        )
        run(
            ["/usr/lib/systemd/systemd-journal-remote", f"--output={path / 'test.journal'}", "-"],
            input=export, text=True, capture_output=True, check=True,
        )

        def read_messages(scope="system", **options):
            entries = read_journal(
                scope, unit,
                reader_factory=lambda: journal.Reader(files=[str(path / "test.journal")]),
                **options,
            )
            return [entry.message for entry in entries]

        assert read_messages() == [
            "Current boot manager message", "Current boot informational message",
        ]
        assert read_messages(boot_id=previous) == [
            "Previous boot unit message", "Previous boot manager message",
        ]
        assert read_messages(limit=1, max_priority=3) == ["Current boot manager message"]
        assert read_messages("user") == [
            "Current boot user manager message", "Current boot user service message",
        ]
        assert read_messages("user", boot_id=previous) == ["Previous boot user manager message"]
    print("Native journal reader keeps both service and manager entries in the selected boot")


if __name__ == "__main__":
    main()
