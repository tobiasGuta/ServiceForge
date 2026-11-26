"""Tests for tray and preferences dialog integration."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gio", "2.0")
gi.require_version("Dbusmenu", "0.4")

from gi.repository import Adw, Gio, GLib  # noqa: E402

from serviceforge.models.settings import Settings  # noqa: E402
from serviceforge.ui.preferences_dialog import PreferencesDialog  # noqa: E402
from serviceforge.ui.tray import ServiceForgeTray  # noqa: E402


class TrayAndPreferencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Adw.init()

    def test_preferences_dialog_updates_settings(self):
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
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
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
