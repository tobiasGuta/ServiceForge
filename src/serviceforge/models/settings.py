"""User preferences and persistent settings for ServiceForge."""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Application settings schema."""

    minimize_to_tray: bool = True
    notify_on_failure: bool = True
    default_scope: str = "system"

    def with_updates(
        self,
        minimize_to_tray: bool | None = None,
        notify_on_failure: bool | None = None,
        default_scope: str | None = None,
    ) -> "Settings":
        return Settings(
            minimize_to_tray=(
                self.minimize_to_tray
                if minimize_to_tray is None
                else bool(minimize_to_tray)
            ),
            notify_on_failure=(
                self.notify_on_failure
                if notify_on_failure is None
                else bool(notify_on_failure)
            ),
            default_scope=(
                self.default_scope
                if default_scope is None
                else (default_scope if default_scope in ("system", "user") else "system")
            ),
        )


def get_default_config_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home) if config_home else Path.home() / ".config"
    return base / "serviceforge" / "config.json"


def load_settings(path: Path | None = None) -> Settings:
    target = path or get_default_config_path()
    if not target.is_file():
        return Settings()

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return Settings()
        return Settings(
            minimize_to_tray=bool(data.get("minimize_to_tray", True)),
            notify_on_failure=bool(data.get("notify_on_failure", True)),
            default_scope=(
                str(data.get("default_scope", "system"))
                if data.get("default_scope") in ("system", "user")
                else "system"
            ),
        )
    except Exception:
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> None:
    target = path or get_default_config_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(asdict(settings), indent=2) + "\n"
        target.write_text(content, encoding="utf-8")
    except Exception:
        pass
