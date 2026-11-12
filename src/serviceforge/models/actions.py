"""Pure action policy for deliberate, read-only-reviewed service management."""

from dataclasses import dataclass
import re

from serviceforge.models.service import ServiceRecord

# Intentionally conservative. Names that contain uncommon escaping stay
# inspectable; they are not eligible for modifications in this early release.
UNIT_PATTERN = re.compile(r"^[A-Za-z0-9_.:@-]+\.service$", re.ASCII)
METHODS = {
    "start": "StartUnit",
    "stop": "StopUnit",
    "restart": "RestartUnit",
    "reload": "ReloadUnit",
}
HIGH_IMPACT_UNITS = frozenset({
    "NetworkManager.service", "systemd-networkd.service",
    "systemd-resolved.service", "sshd.service",
    "gdm.service", "display-manager.service",
    "systemd-logind.service", "polkit.service",
    "dbus.service", "dbus-broker.service",
    "systemd-journald.service", "auditd.service",
})


def validate_unit(name: str) -> bool:
    return (
        isinstance(name, str)
        and len(name) <= 256
        and UNIT_PATTERN.fullmatch(name) is not None
    )


def allowed_actions(record: ServiceRecord, *, can_reload: bool = False) -> set[str]:
    """Suggest actions; systemd remains authoritative about actual support."""
    if not validate_unit(record.name) or record.load_state != "loaded":
        return set()
    if record.unit_file_state in ("masked", "masked-runtime"):
        return set()
    if record.active_state == "active":
        available = {"stop", "restart"}
        if can_reload:
            available.add("reload")
        return available
    if record.active_state in ("inactive", "failed"):
        return {"start"}
    return set()


@dataclass(frozen=True, slots=True)
class ActionOutcome:
    action: str
    unit_name: str
    result: str

    @property
    def succeeded(self) -> bool:
        return self.result == "done"


def confirmation_text(action: str, record: ServiceRecord) -> str:
    """Never describe actions as risk-free; explain possible consequences."""
    if action not in METHODS:
        raise ValueError("Unsupported action")
    messages = {
        "start": "Start this service now. Dependencies may also be activated.",
        "stop": "Stop this service now. Dependent components may be disrupted.",
        "restart": "Restart this service. Existing connections or tasks may be interrupted.",
        "reload": "Request a service configuration reload, if supported.",
    }
    text = messages[action]
    if record.name in HIGH_IMPACT_UNITS:
        text += (
            "\n\nHigh-impact service: this may affect networking, authentication, "
            "desktop access, auditing, or other essential system functions."
        )
    text += (
        "\n\nThis changes runtime state, not whether the unit starts at boot. "
        "Systemd may request Polkit authentication."
    )
    return text
