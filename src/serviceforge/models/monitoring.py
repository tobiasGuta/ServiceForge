"""Pure models for bounded, session-only systemd activity.

Signals tell us that something changed, not necessarily the resulting runtime
state. ServiceForge always fetches an authoritative snapshot separately.
"""

from dataclasses import dataclass
from typing import Sequence

from serviceforge.models.service import Scope


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    scope: Scope
    when: str
    title: str
    detail: str
    unit: str | None = None


class ActivityFeed:
    """A bounded in-memory event feed, never persisted or exported automatically."""

    def __init__(self, max_entries: int = 30) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._limit = max_entries
        self._items: list[ActivityEvent] = []

    def add(self, event: ActivityEvent) -> None:
        self._items.insert(0, event)
        del self._items[self._limit:]

    def recent(self, limit: int = 10) -> tuple[ActivityEvent, ...]:
        return tuple(self._items[:max(0, limit)])


def describe_manager_signal(
    scope: Scope, signal: str, values: Sequence[object], when: str,
) -> ActivityEvent | None:
    """Describe documented Manager signals without claiming service health."""
    if scope not in ("system", "user"):
        raise ValueError("Invalid manager scope")

    if signal in ("UnitNew", "UnitRemoved"):
        if len(values) != 2 or not isinstance(values[0], str):
            return None
        name = values[0]
        if not name.endswith(".service"):
            return None
        title = "Unit loaded" if signal == "UnitNew" else "Unit unloaded"
        return ActivityEvent(
            scope, when, title, "In-memory systemd manager state", name,
        )

    if signal == "JobRemoved":
        if (
            len(values) != 4 or not isinstance(values[2], str)
            or not isinstance(values[3], str)
        ):
            return None
        name, result = values[2], values[3]
        if not name.endswith(".service"):
            return None
        return ActivityEvent(
            scope, when, "Job finished", f"Result: {result}", name,
        )

    if signal == "UnitFilesChanged":
        return ActivityEvent(
            scope, when, "Unit files changed",
            "Startup configuration changed on disk",
        )

    if signal == "Reloading" and tuple(values) == (False,):
        return ActivityEvent(
            scope, when, "Manager reloaded",
            "Systemd completed a configuration reload",
        )
    return None


def should_refresh_for_signal(
    interface: str, signal: str, path: str, values: Sequence[object],
) -> bool:
    """Filter relevant notifications; ignore noisy unrelated properties."""
    if interface == "org.freedesktop.systemd1.Manager":
        return signal in (
            "UnitNew", "UnitRemoved", "JobRemoved",
            "UnitFilesChanged",
        ) or (signal == "Reloading" and tuple(values) == (False,))

    if (
        interface != "org.freedesktop.DBus.Properties"
        or signal != "PropertiesChanged"
        or not path.startswith("/org/freedesktop/systemd1/unit/")
        or len(values) != 3 or not isinstance(values[0], str)
        or not isinstance(values[1], dict)
    ):
        return False

    monitored = {
        "org.freedesktop.systemd1.Unit": {
            "ActiveState", "SubState", "LoadState", "UnitFileState",
        },
        "org.freedesktop.systemd1.Service": {
            "Result", "MainPID", "ExecMainStatus",
        },
    }
    return bool(monitored.get(values[0], set()).intersection(values[1]))
