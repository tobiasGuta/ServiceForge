"""Translate systemd manager replies into strongly typed loaded-service records.

ListUnits rows: (name, description, load, active, sub, following, object_path,
                 job_id, job_type, job_path)
ListUnitFiles rows: (absolute_path, unit_file_state)

ListUnits only returns loaded units. File names may not match instantiated or
transient services; lack of a matching entry must never be called 'disabled'.
"""

from pathlib import PurePosixPath
from typing import Iterable, Sequence

from serviceforge.models.service import Scope, ServiceRecord


def normalize_services(
    unit_rows: Iterable[Sequence[object]],
    unit_file_rows: Iterable[Sequence[object]],
    scope: Scope,
) -> list[ServiceRecord]:
    """Return loaded .service units with known file states, sorted by name."""
    if scope not in ("system", "user"):
        raise ValueError(f"Unrecognized manager scope: {scope!r}")

    file_states: dict[str, str] = {}
    for row in unit_file_rows:
        if len(row) < 2:
            raise ValueError("Malformed ListUnitFiles row")
        path, state = row[:2]
        if isinstance(path, str) and isinstance(state, str):
            file_states.setdefault(PurePosixPath(path).name, state)

    records: list[ServiceRecord] = []
    for row in unit_rows:
        if len(row) < 7:
            raise ValueError("Malformed ListUnits row")
        name, description, load, active, sub = row[:5]
        if not all(
            isinstance(value, str)
            for value in (name, description, load, active, sub)
        ):
            raise ValueError("Unexpected value type in ListUnits row")
        if not name.endswith(".service"):
            continue
        path = row[6] if isinstance(row[6], str) else None
        records.append(
            ServiceRecord(
                scope=scope,
                name=name,
                description=description,
                load_state=load,
                active_state=active,
                sub_state=sub,
                unit_file_state=file_states.get(name),
                object_path=path,
            )
        )
    records.sort(key=lambda record: record.name.casefold())
    return records
