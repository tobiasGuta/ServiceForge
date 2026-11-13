"""Safe, display-ready journald records and pure filtering/formatting helpers."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence


PRIORITY_LABELS = (
    "Emergency", "Alert", "Critical", "Error",
    "Warning", "Notice", "Info", "Debug",
)
MAX_MESSAGE_LENGTH = 8192


@dataclass(frozen=True, slots=True)
class JournalBoot:
    boot_id: str
    first_entry: datetime

    @property
    def label(self) -> str:
        return f"{self.first_entry.astimezone():%Y-%m-%d %H:%M} · {self.boot_id[:8]}"


@dataclass(frozen=True, slots=True)
class JournalEntry:
    timestamp: str
    priority: int | None
    message: str

    @property
    def severity(self) -> str:
        return (
            PRIORITY_LABELS[self.priority]
            if self.priority is not None and 0 <= self.priority <= 7
            else "Unknown"
        )


def normalize_entry(raw: Mapping[str, Any]) -> JournalEntry:
    """Convert one python-systemd entry without assuming optional fields."""
    time = raw.get("__REALTIME_TIMESTAMP")
    if isinstance(time, datetime):
        timestamp = time.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    else:
        timestamp = "Time unknown"
    value = raw.get("PRIORITY")
    try:
        priority = int(value)
        if not (0 <= priority <= 7):
            priority = None
    except (ValueError, TypeError):
        priority = None
    message = raw.get("MESSAGE", "")
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="replace")
    elif not isinstance(message, str):
        message = str(message)
    message = message.replace("\x00", "�")[:MAX_MESSAGE_LENGTH]
    return JournalEntry(timestamp=timestamp, priority=priority, message=message)


def filter_entries(
    entries: Sequence[JournalEntry],
    search: str = "",
    max_priority: int | None = None,
) -> list[JournalEntry]:
    """Priority uses journald semantics: 0 is most severe, 7 is debug."""
    query = search.casefold().strip()
    return [
        entry
        for entry in entries
        if (max_priority is None or (
            entry.priority is not None and entry.priority <= max_priority
        ))
        and (
            not query
            or query in entry.message.casefold()
            or query in entry.timestamp.casefold()
            or query in entry.severity.casefold()
        )
    ]


def format_entries(entries: Sequence[JournalEntry]) -> str:
    """Prepare plain text for the non-editable journal text view."""
    return "\n\n".join(
        f"{entry.timestamp}  [{entry.severity}]\n{entry.message}"
        for entry in entries
    )
