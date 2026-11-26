"""Tests for settings persistence and schema validation."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from serviceforge.models.settings import Settings, load_settings, save_settings  # noqa: E402


class SettingsTests(unittest.TestCase):
    def test_default_settings(self):
        settings = Settings()
        self.assertTrue(settings.minimize_to_tray)
        self.assertTrue(settings.notify_on_failure)
        self.assertEqual(settings.default_scope, "system")

    def test_with_updates(self):
        settings = Settings()
        updated = settings.with_updates(minimize_to_tray=False, default_scope="user")
        self.assertFalse(updated.minimize_to_tray)
        self.assertTrue(updated.notify_on_failure)
        self.assertEqual(updated.default_scope, "user")

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "sub" / "config.json"
            original = Settings(minimize_to_tray=False, notify_on_failure=False, default_scope="user")
            save_settings(original, config_file)

            loaded = load_settings(config_file)
            self.assertEqual(original, loaded)

    def test_corrupted_json_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "config.json"
            config_file.write_text("{bad json: 123", encoding="utf-8")
            loaded = load_settings(config_file)
            self.assertEqual(loaded, Settings())

    def test_invalid_scope_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "config.json"
            config_file.write_text('{"default_scope": "invalid"}', encoding="utf-8")
            loaded = load_settings(config_file)
            self.assertEqual(loaded.default_scope, "system")
