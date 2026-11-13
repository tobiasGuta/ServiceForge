"""Display-ready service inspection data, derived from systemd properties.

There is no inferred security score, service health verdict, or PID. Missing
properties are displayed as unavailable, and a zero MainPID is not a PID.
"""

from dataclasses import dataclass
import shlex
from typing import Any, Mapping

from serviceforge.models.service import Scope


NOT_AVAILABLE = "Not available"


def _string(value: Any, *, empty: str = NOT_AVAILABLE) -> str:
    if isinstance(value, str):
        return value if value else empty
    return empty


def _numeric(value: Any, *, zero: str | None = None) -> str:
    if not isinstance(value, int) or isinstance(value, bool):
        return NOT_AVAILABLE
    if value == 0 and zero is not None:
        return zero
    return str(value)


def _list(value: Any) -> str:
    if not isinstance(value, (list, tuple)):
        return NOT_AVAILABLE
    strings = sorted(item for item in value if isinstance(item, str) and item)
    return "\n".join(strings) if strings else "None reported"


def _commands(value: Any) -> str:
    """Render an ExecStart array's argv where the API exposes it.

    ExecStart records include status/timestamp fields after the executable
    path and argument vector. Those fields are deliberately not interpreted.
    """
    if not isinstance(value, (list, tuple)):
        return NOT_AVAILABLE
    commands: list[str] = []
    for entry in value:
        if not isinstance(entry, (tuple, list)) or len(entry) < 2:
            continue
        path, argv = entry[0], entry[1]
        if not isinstance(path, str) or not isinstance(argv, (tuple, list)):
            continue
        if not all(isinstance(arg, str) for arg in argv):
            continue
        commands.append(shlex.join(argv) if argv else shlex.quote(path))
    return "\n".join(commands) if commands else NOT_AVAILABLE


@dataclass(frozen=True, slots=True)
class ServiceDetails:
    """Systemd's Unit and Service interface properties for a loaded service."""

    scope: Scope
    requested_name: str
    unit: Mapping[str, Any]
    service: Mapping[str, Any]
    service_warning: str | None = None
    object_path: str | None = None

    @property
    def display_name(self) -> str:
        return _string(self.unit.get("Id"), empty=self.requested_name)

    @property
    def failure_summary(self) -> str | None:
        if self.unit.get("ActiveState") != "failed":
            return None
        result = _string(self.service.get("Result"))
        code = self.service.get("ExecMainCode")
        status = _numeric(self.service.get("ExecMainStatus"))
        if code in (2, 3):
            execution = f"Signal {status}" if status != NOT_AVAILABLE else status
        elif code == 1:
            execution = f"Exit status {status}" if status != NOT_AVAILABLE else status
        else:
            execution = "Exit status unavailable"
        restarts = _numeric(self.service.get("NRestarts"))
        return f"Result: {result} · {execution} · Restarts: {restarts}"

    def sections(self) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
        """Generate human-readable rows without assuming absent values."""
        unit = self.unit
        service = self.service
        startup_state = _string(unit.get("UnitFileState"))
        drop_ins = _list(unit.get("DropInPaths"))
        return (
            (
                "Identity and state",
                (
                    ("Description", _string(unit.get("Description"))),
                    ("Manager", "System" if self.scope == "system" else "User"),
                    ("Load state", _string(unit.get("LoadState"))),
                    ("Active state", _string(unit.get("ActiveState"))),
                    ("Substate", _string(unit.get("SubState"))),
                    ("Unit-file state", startup_state),
                    ("Unit file", _string(unit.get("FragmentPath"))),
                    ("Source file", _string(unit.get("SourcePath"))),
                    ("Drop-in overrides", drop_ins),
                ),
            ),
            (
                "Execution",
                (
                    ("Service type", _string(service.get("Type"))),
                    ("Current main PID", _numeric(service.get("MainPID"), zero="No current main PID")),
                    ("Most recent main PID", _numeric(service.get("ExecMainPID"), zero="Not reported")),
                    ("Configured user", _string(service.get("User"), empty="Manager default")),
                    ("Configured group", _string(service.get("Group"), empty="Manager default")),
                    ("ExecStart commands", _commands(service.get("ExecStart"))),
                    ("Restart policy", _string(service.get("Restart"))),
                    ("Restart counter", _numeric(service.get("NRestarts"))),
                    ("Last service result", _string(service.get("Result"))),
                    ("Last execution code", _numeric(service.get("ExecMainCode"))),
                    ("Last execution status", _numeric(service.get("ExecMainStatus"))),
                    ("Control group", _string(service.get("ControlGroup"))),
                ),
            ),
            (
                "Dependencies and ordering",
                (
                    ("Requires", _list(unit.get("Requires"))),
                    ("Wants", _list(unit.get("Wants"))),
                    ("After (ordering)", _list(unit.get("After"))),
                    ("Before (ordering)", _list(unit.get("Before"))),
                    ("Conflicts", _list(unit.get("Conflicts"))),
                ),
            ),
        )
