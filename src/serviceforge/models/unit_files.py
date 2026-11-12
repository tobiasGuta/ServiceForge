"""Conservative, pure policy for persistent systemd unit-file operations.

This covers only existing concrete .service unit files. Systemd's states
are not boolean: static, indirect, generated, alias, transient, linked and
runtime-only enablement/masks require distinct handling not implemented here.
"""

from dataclasses import dataclass

from serviceforge.models.actions import HIGH_IMPACT_UNITS, validate_unit
from serviceforge.models.service import Scope, ServiceRecord


FILE_METHODS = {
    "enable": "EnableUnitFiles",
    "disable": "DisableUnitFiles",
    "mask": "MaskUnitFiles",
    "unmask": "UnmaskUnitFiles",
}
EXPECTED_STATES = {
    "enable": "disabled",
    "disable": "enabled",
    "mask": "disabled",
    "unmask": "masked",
}
# Never offer persistent file operations on core manager/auth/network units
# while this feature is still experimental. This blocklist is deliberately
# restrictive and not a claim of comprehensive risk assessment.
PROTECTED_PREFIXES = (
    "systemd-", "dbus-", "NetworkManager-", "getty@", "serial-getty@",
    "user@", "system-", "selinux-",
)


def file_action_allowed(
    record: ServiceRecord,
    action: str,
    state: str | None,
    *,
    active_state: str | None = None,
) -> bool:
    """Require a real observed file, a simple state, and a safe operation."""
    if action not in FILE_METHODS or not validate_unit(record.name):
        return False
    if not record.unit_file_path or not record.unit_file_path.startswith("/"):
        return False
    if record.scope not in ("user", "system"):
        return False
    if record.scope == "system" and (
        record.name in HIGH_IMPACT_UNITS
        or record.name.startswith(PROTECTED_PREFIXES)
    ):
        return False
    if state != EXPECTED_STATES[action]:
        return False
    # Masking can prevent activation through dependencies or socket triggers.
    # Force the operator to stop a unit first, without doing it automatically.
    if action == "mask" and active_state != "inactive":
        return False
    return True


def file_action_message(action: str, record: ServiceRecord) -> str:
    if action not in FILE_METHODS:
        raise ValueError("Unknown file operation")
    messages = {
        "enable": (
            "Create persistent startup symlinks according to the unit's "
            "[Install] section. This does not start the service now."
        ),
        "disable": (
            "Remove this service's persistent startup symlinks. This does "
            "not stop a running service and can affect future activations."
        ),
        "mask": (
            "Prevent this service from being activated by linking it to "
            "/dev/null. Masking may break other services that depend on it. "
            "It does not stop an already-running service."
        ),
        "unmask": (
            "Remove the persistent /dev/null mask. Unmasking does not "
            "automatically enable or start this service."
        ),
    }
    return (
        messages[action]
        + "\n\nThe change persists across reboots and may require systemd's "
        "Polkit authorization. ServiceForge never forces symlink replacement "
        "and will not automatically start or stop the service."
        + ("\n\nSystem scope: this affects system-wide configuration."
           if record.scope == "system" else "")
    )


def requires_typed_confirmation(record: ServiceRecord, action: str) -> bool:
    """Provide a second intentional step for masking and system-wide changes."""
    return action in ("mask", "unmask") or record.scope == "system"


@dataclass(frozen=True, slots=True)
class FileActionOutcome:
    action: str
    unit_name: str
    previous_state: str
    current_state: str
    changes: tuple[tuple[str, str, str], ...]
    install_info: bool | None

    @property
    def verified(self) -> bool:
        if self.action in ("enable", "disable", "mask"):
            return self.current_state == {
                "enable": "enabled",
                "disable": "disabled",
                "mask": "masked",
            }[self.action]
        return self.action == "unmask" and self.current_state not in (
            "masked", "masked-runtime"
        )
