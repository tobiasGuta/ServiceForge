"""Reconcile loaded systemd units with installed .service unit files.

`ListUnits` contains currently loaded units and accurate runtime state.
`ListUnitFiles` contains unit files, including ones systemd unloaded.

Unloaded entries intentionally display no made-up ActiveState or SubState.
An instance may not have an exact basename match with a template unit file.
"""

from pathlib import PurePosixPath
from typing import Iterable, Sequence

from serviceforge.models.service import Scope, ServiceRecord


def normalize_services(
    unit_rows: Iterable[Sequence[object]],
    unit_file_rows: Iterable[Sequence[object]],
    scope: Scope,
) -> list[ServiceRecord]:
    """Combine loaded services with installed-but-unloaded concrete unit files."""
    if scope not in ("system", "user"):
        raise ValueError(f"Unrecognized manager scope: {scope!r}")

    files: dict[str, tuple[str, str]] = {}
    for row in unit_file_rows:
        if len(row) < 2:
            raise ValueError("Malformed ListUnitFiles row")
        path, state = row[:2]
        if isinstance(path, str) and isinstance(state, str):
            name = PurePosixPath(path).name
            if name.endswith(".service"):
                files.setdefault(name, (path, state))

    records: list[ServiceRecord] = []
    loaded_names: set[str] = set()
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
        file_info = files.get(name)
        records.append(
            ServiceRecord(
                scope=scope,
                name=name,
                description=description,
                load_state=load,
                active_state=active,
                sub_state=sub,
                unit_file_state=file_info[1] if file_info else None,
                object_path=path,
                loaded=True,
                unit_file_path=file_info[0] if file_info else None,
            )
        )
        loaded_names.add(name)

    for name, (path, state) in files.items():
        # A bare template (foo@.service) requires an instance parameter.
        # It must not be presented as an ordinary startable unit.
        if name in loaded_names or name.endswith("@.service"):
            continue
        records.append(
            ServiceRecord(
                scope=scope,
                name=name,
                description="Unit file available (not currently loaded)",
                load_state="unloaded",
                active_state="unknown",
                sub_state="unknown",
                unit_file_state=state,
                object_path=None,
                loaded=False,
                unit_file_path=path,
            )
        )
    records.sort(key=lambda record: record.name.casefold())
    return records
