"""Bounded journald history, queried only on demand.

python3-systemd is imported lazily so missing journal support does not prevent
ServiceForge's D-Bus service explorer from launching.
"""

from collections.abc import Callable
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from datetime import datetime
from functools import partial
import os
from typing import Any, TypeVar

from serviceforge.models.journal import JournalBoot, JournalEntry, normalize_entry
from serviceforge.models.service import Scope


MAX_JOURNAL_ROWS = 200
LogCallback = Callable[[list[JournalEntry]], None]
ErrorCallback = Callable[[str], None]
T = TypeVar("T")


def _open_journal() -> Any:
    try:
        from systemd import journal
    except ImportError as exc:
        raise RuntimeError(
            "Journal support is unavailable. Install Fedora package python3-systemd."
        ) from exc
    return journal.Reader()


def list_previous_boots() -> list[JournalBoot]:
    """Return readable previous boots, ordered by first recorded entry."""
    with _open_journal() as reader:
        from systemd import id128

        current_boot = id128.get_boot()
        boots: list[JournalBoot] = []
        for boot in reader.query_unique("_BOOT_ID") - {current_boot}:
            reader.flush_matches()
            reader.this_boot(boot.hex)
            reader.seek_head()
            first_entry = reader.get_next().get("__REALTIME_TIMESTAMP")
            if isinstance(first_entry, datetime):
                boots.append(JournalBoot(boot.hex, first_entry))
    return sorted(boots, key=lambda boot: boot.first_entry, reverse=True)


def read_journal(
    scope: Scope,
    unit_name: str,
    *,
    limit: int = MAX_JOURNAL_ROWS,
    boot_id: str | None = None,
    max_priority: int | None = None,
    reader_factory: Callable[[], Any] | None = None,
    uid: int | None = None,
) -> list[JournalEntry]:
    """Return up to *limit* readable messages for one boot in chronological order.

    Matches messages emitted by the service plus selected systemd manager
    messages about the service, similar to journalctl -u/--user-unit.
    The query still observes journal access permissions.
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
    if boot_id is not None and (
        len(boot_id) != 32 or any(char not in "0123456789abcdef" for char in boot_id)
    ):
        raise ValueError("Invalid journal boot ID")
    if max_priority is not None and not 0 <= max_priority <= 7:
        raise ValueError("Invalid journal priority limit")

    reader = (reader_factory or _open_journal)()
    try:
        reader.this_boot(boot_id)
        # Apply the boot match to every branch below.
        reader.add_conjunction()
        if scope == "system":
            # Branch 1: messages emitted by the unit itself.
            reader.add_match(_SYSTEMD_UNIT=unit_name)
            # Branch 2: PID 1 logging about the unit.
            reader.add_disjunction()
            reader.add_match(UNIT=unit_name, _PID="1")
            # Branch 3: manager-referenced object unit.
            reader.add_disjunction()
            reader.add_match(OBJECT_SYSTEMD_UNIT=unit_name, _UID="0")
        else:
            current_uid = str(os.getuid() if uid is None else uid)
            reader.add_match(_SYSTEMD_USER_UNIT=unit_name, _UID=current_uid)
            # User manager lifecycle messages about the unit.
            reader.add_disjunction()
            reader.add_match(USER_UNIT=unit_name, _UID=current_uid)
        if max_priority is not None:
            reader.add_conjunction()
            for priority in range(max_priority + 1):
                reader.add_match(PRIORITY=str(priority))
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
        *,
        boot_id: str | None = None,
        limit: int = MAX_JOURNAL_ROWS,
        max_priority: int | None = None,
    ) -> Future[list[JournalEntry]]:
        return self._submit(
            partial(
                read_journal, scope, unit_name, boot_id=boot_id,
                limit=limit, max_priority=max_priority,
            ),
            on_success, on_error,
        )

    def fetch_boots(
        self, on_success: Callable[[list[JournalBoot]], None], on_error: ErrorCallback,
    ) -> Future[list[JournalBoot]]:
        return self._submit(list_previous_boots, on_success, on_error)

    def _submit(
        self, read: Callable[[], T], on_success: Callable[[T], None],
        on_error: ErrorCallback,
    ) -> Future[T]:
        from gi.repository import GLib

        future = self._executor.submit(read)

        def completed(done: Future[T]) -> None:
            try:
                result = done.result()
            except CancelledError:
                return
            except Exception as exc:
                # Preserve the message: Python clears exception variables when
                # leaving an except block (before GLib calls this callback).
                message = str(exc)
                def publish_error() -> bool:
                    on_error(message)
                    return GLib.SOURCE_REMOVE

                GLib.idle_add(publish_error)
            else:
                def publish_success() -> bool:
                    on_success(result)
                    return GLib.SOURCE_REMOVE

                GLib.idle_add(publish_success)

        future.add_done_callback(completed)
        return future

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
