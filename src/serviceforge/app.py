"""Top-level Libadwaita application."""

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

from serviceforge import __version__
from serviceforge.models.settings import Settings, load_settings
from serviceforge.ui.main_window import MainWindow
from serviceforge.ui.preferences_dialog import PreferencesDialog
from serviceforge.ui.tray import ServiceForgeTray


APP_ID = "io.github.tobiasGuta.ServiceForge"


class ServiceForgeApplication(Adw.Application):
    """An unprivileged desktop application using the systemd D-Bus API."""

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._settings: Settings = load_settings()
        self._tray: ServiceForgeTray | None = None
        self._window: MainWindow | None = None
        self._holding = False

        self.connect("startup", self._on_startup)

        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", self._show_about)
        self.add_action(about)

        prefs = Gio.SimpleAction.new("preferences", None)
        prefs.connect("activate", self._show_preferences)
        self.add_action(prefs)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self._on_quit_action)
        self.add_action(quit_action)

        open_action = Gio.SimpleAction.new("open", None)
        open_action.connect("activate", lambda *_: self.present_window())
        self.add_action(open_action)

    @property
    def minimize_to_tray(self) -> bool:
        return self._settings.minimize_to_tray

    @property
    def default_scope(self) -> str:
        return self._settings.default_scope

    @property
    def tray_available(self) -> bool:
        return self._tray is not None and self._tray.is_available

    def _on_startup(self, *_args: object) -> None:
        local_icons = Path(__file__).resolve().parent.parent.parent / "data" / "icons"
        if local_icons.exists():
            display = Gdk.Display.get_default()
            if display is not None:
                theme = Gtk.IconTheme.get_for_display(display)
                theme.add_search_path(str(local_icons))

        self._setup_tray()

    def _setup_tray(self) -> None:
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._tray = ServiceForgeTray(
                connection=bus,
                app_id=APP_ID,
                on_open=self.present_window,
                on_preferences=lambda: self._show_preferences(None),
                on_quit=self.quit_app,
                on_toggle_live=self._on_tray_toggle_live,
            )
            self._sync_hold()
        except Exception:
            self._tray = None
            self._sync_hold()

    def _sync_hold(self) -> None:
        should_hold = self.tray_available and self._settings.minimize_to_tray
        if should_hold and not self._holding:
            self.hold()
            self._holding = True
        elif not should_hold and self._holding:
            self.release()
            self._holding = False

    def _on_tray_toggle_live(self, active: bool) -> None:
        if self._window is not None:
            self._window.toggle_live_monitoring(active)

    def set_tray_live_active(self, active: bool) -> None:
        if self._tray is not None:
            self._tray.set_live_active(active)

    def update_tray_status(
        self, failed_count: int, total_count: int, scope: str = "system"
    ) -> None:
        if self._tray is not None:
            self._tray.update_status(failed_count, total_count, scope)

    def notify_failure(self, service_name: str, message: str) -> None:
        if not self._settings.notify_on_failure:
            return
        try:
            notif = Gio.Notification.new(f"Service Failure: {service_name}")
            notif.set_body(message)
            notif.set_default_action("app.open")
            self.send_notification(f"failed-{service_name}", notif)
        except Exception:
            pass

    def _show_preferences(self, *_args: object) -> None:
        dialog = PreferencesDialog(
            self._settings,
            on_change=self._on_settings_changed,
        )
        target = self.props.active_window or self._window
        dialog.present(target)

    def _on_settings_changed(self, new_settings: Settings) -> None:
        self._settings = new_settings
        self._sync_hold()

    def _show_about(self, *_args: object) -> None:
        dialog = Adw.AboutDialog(
            application_name="ServiceForge",
            application_icon=APP_ID,
            developer_name="ServiceForge contributors",
            version=__version__,
            website="https://github.com/tobiasGuta/ServiceForge",
            issue_url="https://github.com/tobiasGuta/ServiceForge/issues",
            license_type=Gtk.License.GPL_3_0,
            copyright="© 2026 Tobias Guta",
        )
        dialog.present(self.props.active_window)

    def present_window(self) -> None:
        if self._window is None:
            self.activate()
        else:
            self._window.set_visible(True)
            self._window.present()

    def _on_quit_action(self, *_args: object) -> None:
        self.quit_app()

    def on_window_closed(self) -> None:
        self._window = None
        if self._tray is not None:
            self._tray.destroy()
            self._tray = None
        self._sync_hold()
        self.quit()

    def quit_app(self) -> None:
        if self._window is not None:
            window = self._window
            self._window = None
            window.force_close()
        if self._tray is not None:
            self._tray.destroy()
            self._tray = None
        self._sync_hold()
        self.quit()

    def do_activate(self) -> None:
        if self._window is None:
            self._window = MainWindow(application=self)
        self._window.set_visible(True)
        self._window.present()
