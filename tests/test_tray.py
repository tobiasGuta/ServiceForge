"""Tests for tray and preferences dialog integration."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Gio", "2.0")
    gi.require_version("Dbusmenu", "0.4")

    from gi.repository import Adw, Gdk, Gio, Gtk  # noqa: E402

    from serviceforge.app import ServiceForgeApplication  # noqa: E402
    from serviceforge.models.settings import Settings  # noqa: E402
    from serviceforge.ui.preferences_dialog import PreferencesDialog  # noqa: E402
    from serviceforge.ui.tray import ServiceForgeTray  # noqa: E402

    GTK_AVAILABLE = True
except (ImportError, ValueError):
    GTK_AVAILABLE = False


@unittest.skipUnless(GTK_AVAILABLE, "GTK4, Libadwaita, and Dbusmenu typelibs required")
class TrayAndPreferencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Gtk.init_check()
        if Gdk.Display.get_default() is not None:
            Adw.init()

    def test_preferences_dialog_updates_settings(self):
        if Gdk.Display.get_default() is None:
            self.skipTest("Display required for GTK widget tests")
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_config = Path(tmp) / "config.json"
            updated: list[Settings] = []
            initial = Settings(minimize_to_tray=True, notify_on_failure=True, default_scope="system")

            dialog = PreferencesDialog(
                initial,
                on_change=lambda s: updated.append(s),
                config_path=tmp_config,
            )

            # Toggle minimize
            dialog._minimize_switch.set_active(False)
            self.assertTrue(len(updated) >= 1)
            self.assertFalse(updated[-1].minimize_to_tray)

            # Toggle notification
            dialog._notify_switch.set_active(False)
            self.assertFalse(updated[-1].notify_on_failure)

            # Change scope
            dialog._scope_combo.set_selected(1)
            self.assertEqual(updated[-1].default_scope, "user")

    def test_tray_initialization_and_status(self):
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception as exc:
            self.skipTest(f"Session D-Bus unavailable: {exc}")
        actions = []

        tray = ServiceForgeTray(
            connection=bus,
            app_id="io.github.tobiasGuta.ServiceForge.Test",
            on_open=lambda: actions.append("open"),
            on_preferences=lambda: actions.append("prefs"),
            on_quit=lambda: actions.append("quit"),
            on_toggle_live=lambda active: actions.append(f"live:{active}"),
        )

        self.assertIsNotNone(tray._menu_server)
        self.assertTrue(tray._registration_id > 0)

        # Verify property querying
        title_var = tray._handle_get_property(bus, "", "", "", "Title")
        self.assertEqual(title_var.get_string(), "ServiceForge")

        status_var = tray._handle_get_property(bus, "", "", "", "Status")
        self.assertEqual(status_var.get_string(), "Active")

        # Update status with failures
        tray.update_status(failed_count=3, total_count=120, scope="system")
        status_var = tray._handle_get_property(bus, "", "", "", "Status")
        self.assertEqual(status_var.get_string(), "NeedsAttention")

        # Test live toggle
        tray.set_live_active(False)
        self.assertFalse(tray._live_active)
        tray.set_live_active(True)
        self.assertTrue(tray._live_active)

        # Cleanup
        tray.destroy()
        self.assertEqual(tray._registration_id, 0)

    def test_application_releases_hold_and_quits_when_minimize_to_tray_disabled(self):
        with patch(
            "serviceforge.app.load_settings",
            return_value=Settings(minimize_to_tray=True),
        ):
            app = ServiceForgeApplication()

        fake_tray = MagicMock()
        fake_tray.is_available = True
        app._tray = fake_tray
        with patch.object(app, "hold") as hold_mock, patch.object(
            app, "release"
        ) as release_mock, patch.object(app, "quit") as quit_mock:
            app._sync_hold()
            hold_mock.assert_called_once()
            self.assertTrue(app._holding)

            # Turning off minimize_to_tray releases hold immediately.
            app._on_settings_changed(Settings(minimize_to_tray=False))
            release_mock.assert_called_once()
            self.assertFalse(app._holding)

            # Closing the window tears down tray and quits without lingering headless.
            app._window = MagicMock()
            app.on_window_closed()
            fake_tray.destroy.assert_called_once()
            self.assertIsNone(app._window)
            self.assertIsNone(app._tray)
            quit_mock.assert_called_once()
