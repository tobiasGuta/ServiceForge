"""Top-level Libadwaita application."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk  # noqa: E402

from serviceforge import __version__
from serviceforge.ui.main_window import MainWindow


APP_ID = "io.github.tobiasGuta.ServiceForge"


class ServiceForgeApplication(Adw.Application):
    """An unprivileged desktop application using the systemd D-Bus API."""

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", self._show_about)
        self.add_action(about)

    def _show_about(self, *_args: object) -> None:
        dialog = Adw.AboutDialog(
            application_name="ServiceForge",
            application_icon="applications-system-symbolic",
            developer_name="ServiceForge contributors",
            version=__version__,
            website="https://github.com/tobiasGuta/ServiceForge",
            issue_url="https://github.com/tobiasGuta/ServiceForge/issues",
            license_type=Gtk.License.GPL_3_0,
            copyright="© 2026 Tobias Guta",
        )
        dialog.present(self.props.active_window)

    def do_activate(self) -> None:
        window = self.props.active_window
        if window is None:
            window = MainWindow(application=self)
        window.present()
