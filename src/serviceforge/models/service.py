"""Typed, immutable records for loaded units and installed unit files."""

from dataclasses import dataclass
from typing import Literal


Scope = Literal["system", "user"]


@dataclass(frozen=True, slots=True)
class ServiceRecord:
    scope: Scope
    name: str
    description: str
    load_state: str
    active_state: str
    sub_state: str
    unit_file_state: str | None
    object_path: str | None = None
    loaded: bool = True
    unit_file_path: str | None = None

    @property
    def startup_display(self) -> str:
        return self.unit_file_state if self.unit_file_state is not None else "Unknown"
