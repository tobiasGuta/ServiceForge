"""Read-only summary calculations over the currently loaded services."""

from dataclasses import dataclass
from typing import Iterable

from serviceforge.models.service import ServiceRecord


@dataclass(frozen=True, slots=True)
class ServiceSnapshot:
    total: int
    active: int
    inactive: int
    failed: int
    other: int
    failed_units: tuple[ServiceRecord, ...]


def summarize_services(records: Iterable[ServiceRecord]) -> ServiceSnapshot:
    """Count actual ActiveState values, without treating inactive as failed."""
    rows = tuple(records)
    active = sum(item.active_state == "active" for item in rows)
    inactive = sum(item.active_state == "inactive" for item in rows)
    failed = sum(item.active_state == "failed" for item in rows)
    return ServiceSnapshot(
        total=len(rows),
        active=active,
        inactive=inactive,
        failed=failed,
        other=len(rows) - active - inactive - failed,
        failed_units=tuple(sorted(
            (item for item in rows if item.active_state == "failed"),
            key=lambda item: item.name.casefold(),
        )),
    )
