"""Preferences dialog for ServiceForge."""

from pathlib import Path
from typing import Callable
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from serviceforge.models.settings import Settings, save_settings


class PreferencesDialog(Adw.PreferencesDialog):
    """Configures application behavior and tray preferences."""

    def __init__(
        self,
        settings: Settings,
        on_change: Callable[[Settings], None] | None = None,
        config_path: Path | None = None,
    ) -> None:
        super().__init__(title="Preferences")
        self._settings = settings
        self._on_change = on_change
        self._config_path = config_path

        page = Adw.PreferencesPage(
            title="General",
            icon_name="preferences-system-symbolic",
        )
        self.add(page)

        # Background & Tray group
        tray_group = Adw.PreferencesGroup(
            title="Background and System Tray",
            description="Control how ServiceForge behaves when minimized or running in the tray.",
        )
        page.add(tray_group)

        self._minimize_switch = Adw.SwitchRow(
            title="Minimize to tray on close",
            subtitle="Keep ServiceForge running in the background when the window is closed",
            active=self._settings.minimize_to_tray,
        )
        self._minimize_switch.connect("notify::active", self._on_minimize_toggled)
        tray_group.add(self._minimize_switch)

        self._notify_switch = Adw.SwitchRow(
            title="Notify on service failure",
            subtitle="Show a desktop notification when a monitored service enters the failed state",
            active=self._settings.notify_on_failure,
        )
        self._notify_switch.connect("notify::active", self._on_notify_toggled)
        tray_group.add(self._notify_switch)

        # Startup group
        startup_group = Adw.PreferencesGroup(
            title="Startup",
            description="Configure startup preferences.",
        )
        page.add(startup_group)

        self._scope_combo = Adw.ComboRow(
            title="Default manager scope",
            subtitle="The systemd manager selected on launch",
            model=Gtk.StringList.new(["System services", "User services"]),
            selected=0 if self._settings.default_scope == "system" else 1,
        )
        self._scope_combo.connect("notify::selected", self._on_scope_changed)
        startup_group.add(self._scope_combo)

    def _on_minimize_toggled(self, *_args: object) -> None:
        self._update(minimize_to_tray=self._minimize_switch.get_active())

    def _on_notify_toggled(self, *_args: object) -> None:
        self._update(notify_on_failure=self._notify_switch.get_active())

    def _on_scope_changed(self, *_args: object) -> None:
        scope = "system" if self._scope_combo.get_selected() == 0 else "user"
        self._update(default_scope=scope)

    def _update(self, **kwargs: object) -> None:
        self._settings = self._settings.with_updates(**kwargs)
        save_settings(self._settings, self._config_path)
        if self._on_change:
            self._on_change(self._settings)
