"""Bounded journald history, queried only on demand.

python3-systemd is imported lazily so missing journal support does not prevent
ServiceForge's D-Bus service explorer from launching.
"""

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
import os
from typing import Any

from serviceforge.models.journal import JournalEntry, normalize_entry
from serviceforge.models.service import Scope


MAX_JOURNAL_ROWS = 200
LogCallback = Callable[[list[JournalEntry]], None]
ErrorCallback = Callable[[str], None]


def read_journal(
    scope: Scope,
    unit_name: str,
    *,
    limit: int = MAX_JOURNAL_ROWS,
    reader_factory: Callable[[], Any] | None = None,
    uid: int | None = None,
) -> list[JournalEntry]:
    """Return up to *limit* readable messages for this boot in chronological order.

    A user manager's unit is matched by _SYSTEMD_USER_UNIT and _UID, not by the
    global _SYSTEMD_UNIT field. No shell is used, no permissions are changed.
    """
    if scope not in ("system", "user"):
        raise ValueError("Invalid manager scope")
    if (
        not unit_name.endswith(".service")
        or len(unit_name) > 256
        or any(char in unit_name for char in ("/", "\x00", "\n", "\r"))
    ):
        raise ValueError("Invalid systemd service name")
    if not isinstance(limit, int) or not (1 <= limit <= MAX_JOURNAL_ROWS):
        raise ValueError("Invalid journal entry limit")

    if reader_factory is None:
        try:
            from systemd import journal
        except ImportError as exc:
            raise RuntimeError(
                "Journal support is unavailable. Install Fedora package python3-systemd."
            ) from exc
        reader_factory = journal.Reader

    reader = reader_factory()
    try:
        reader.this_boot()
        if scope == "system":
            reader.add_match(_SYSTEMD_UNIT=unit_name)
        else:
            reader.add_match(_SYSTEMD_USER_UNIT=unit_name)
            reader.add_match(_UID=str(os.getuid() if uid is None else uid))
        reader.seek_tail()
        entries: list[JournalEntry] = []
        for _ in range(limit):
            raw = reader.get_previous()
            if not raw:
                break
            entries.append(normalize_entry(raw))
        entries.reverse()
        return entries
    finally:
        reader.close()


class JournalClient:
    """Fetch journal history off the UI thread and publish via GLib idle."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="serviceforge-journal")

    def fetch(
        self,
        scope: Scope,
        unit_name: str,
        on_success: LogCallback,
        on_error: ErrorCallback,
    ) -> None:
        from gi.repository import GLib

        future = self._executor.submit(read_journal, scope, unit_name)

        def completed(done: Any) -> None:
            try:
                entries = done.result()
            except Exception as exc:
                # Journal access can fail with EACCES, missing files, or an
                # unavailable optional Fedora dependency; never elevate.
                def publish_error() -> bool:
                    on_error(str(exc))
                    return GLib.SOURCE_REMOVE

                GLib.idle_add(publish_error)
            else:
                def publish_success() -> bool:
                    on_success(entries)
                    return GLib.SOURCE_REMOVE

                GLib.idle_add(publish_success)

        future.add_done_callback(completed)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
