"""Top-level Libadwaita application."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio  # noqa: E402

from serviceforge.ui.main_window import MainWindow


APP_ID = "io.github.tobiasGuta.ServiceForge"


class ServiceForgeApplication(Adw.Application):
    """An unprivileged desktop application; all operations are read-only."""

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self) -> None:
        window = self.props.active_window
        if window is None:
            window = MainWindow(application=self)
        window.present()
