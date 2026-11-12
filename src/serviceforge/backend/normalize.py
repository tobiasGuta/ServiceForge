"""Pure functions translating systemd manager replies into service records.

ListUnits rows contain:
(name, description, load_state, active_state, sub_state, following,
 object_path, job_id, job_type, job_path)

ListUnitFiles rows contain (unit_file_path, unit_file_state).

A missing match is unknown, not disabled. This first release intentionally
shows loaded units only; installed but unloaded units require a separate view.
"""

from pathlib import PurePosixPath
from typing import Iterable, Sequence

from serviceforge.models.service import Scope, ServiceRecord


def normalize_services(
    unit_rows: Iterable[Sequence[object]],
    unit_file_rows: Iterable[Sequence[object]],
    scope: Scope,
) -> list[ServiceRecord]:
    """Keep loaded .service units and attach known startup configuration."""
    if scope not in ("system", "user"):
        raise ValueError(f"Unrecognized manager scope: {scope!r}")

    file_states: dict[str, str] = {}
    for row in unit_file_rows:
        if len(row) < 2:
            raise ValueError("Malformed ListUnitFiles row")
        path, state = row[:2]
        if isinstance(path, str) and isinstance(state, str):
            unit_name = PurePosixPath(path).name
            # Prefer the first occurrence rather than arbitrarily overriding
            # duplicate unit names with a potentially different definition.
            file_states.setdefault(unit_name, state)

    services: list[ServiceRecord] = []
    for row in unit_rows:
        if len(row) < 5:
            raise ValueError("Malformed ListUnits row")
        name, description, load, active, sub = row[:5]
        if not all(isinstance(value, str) for value in (name, description, load, active, sub)):
            raise ValueError("Unexpected value type in ListUnits row")
        if not name.endswith(".service"):
            continue
        services.append(
            ServiceRecord(
                scope=scope,
                name=name,
                description=description,
                load_state=load,
                active_state=active,
                sub_state=sub,
                unit_file_state=file_states.get(name),
            )
        )
    services.sort(key=lambda record: record.name.casefold())
    return services
