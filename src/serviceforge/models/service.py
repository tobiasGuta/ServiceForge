"""Service state as reported by systemd, without invented defaults."""

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

    @property
    def startup_display(self) -> str:
        return self.unit_file_state if self.unit_file_state is not None else "Unknown"
