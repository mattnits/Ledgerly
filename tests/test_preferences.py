import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.ui.preferences import (
    last_user_id,
    open_fullscreen_enabled,
    save_imported_files_enabled,
    set_last_user_id,
    set_open_fullscreen,
    set_save_imported_files,
)
from app.ui.pages.settings import SettingsPage


class MemorySettings:
    def __init__(self) -> None:
        self.values = {}

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value) -> None:
        self.values[key] = value

    def sync(self) -> None:
        pass

    def remove(self, key) -> None:
        self.values.pop(key, None)


class PreferencesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_fullscreen_is_the_default_and_can_be_persisted(self):
        settings = MemorySettings()

        self.assertTrue(open_fullscreen_enabled(settings))
        set_open_fullscreen(False, settings)
        self.assertFalse(open_fullscreen_enabled(settings))
        set_open_fullscreen(True, settings)
        self.assertTrue(open_fullscreen_enabled(settings))

    def test_settings_toggle_saves_and_announces_the_window_mode(self):
        with (
            patch("app.ui.pages.settings.open_fullscreen_enabled", return_value=True),
            patch("app.ui.pages.settings.set_open_fullscreen") as save_preference,
        ):
            page = SettingsPage()
            changes = QSignalSpy(page.fullscreen_preference_changed)

            self.assertTrue(page.open_fullscreen)
            page.fullscreen_toggle.click()

            save_preference.assert_called_once_with(False)
            self.assertFalse(page.open_fullscreen)
            self.assertEqual(changes.count(), 1)
            page.close()

    def test_import_file_archiving_defaults_on_and_can_be_persisted(self):
        settings = MemorySettings()

        self.assertTrue(save_imported_files_enabled(settings))
        set_save_imported_files(False, settings)
        self.assertFalse(save_imported_files_enabled(settings))

    def test_last_user_is_cached_and_can_be_cleared(self):
        settings = MemorySettings()

        self.assertIsNone(last_user_id(settings))
        set_last_user_id("user-2", settings)
        self.assertEqual(last_user_id(settings), "user-2")
        set_last_user_id(None, settings)
        self.assertIsNone(last_user_id(settings))

    def test_settings_controls_the_import_dialog_default(self):
        with (
            patch("app.ui.pages.settings.open_fullscreen_enabled", return_value=True),
            patch("app.ui.pages.settings.save_imported_files_enabled", return_value=True),
            patch("app.ui.pages.settings.set_save_imported_files") as save_preference,
        ):
            page = SettingsPage()
            self.assertTrue(page.save_import_files_toggle.isChecked())

            page.save_import_files_toggle.click()

            save_preference.assert_called_once_with(False)
            page.close()


if __name__ == "__main__":
    unittest.main()
