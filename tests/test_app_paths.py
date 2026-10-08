import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.paths import (
    app_data_dir,
    import_archive_dir,
    import_archive_label,
    prepare_app_data_dir,
)


class AppPathsTest(unittest.TestCase):
    def test_source_checkout_keeps_existing_data_location(self):
        with patch.object(sys, "frozen", False, create=True):
            location = app_data_dir()
            self.assertEqual(location, Path(__file__).resolve().parent.parent / "data")
            self.assertEqual(import_archive_label(), "data/imported_statements")

    def test_windows_build_uses_local_app_data(self):
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "platform", "win32"),
            patch.dict(os.environ, {"LOCALAPPDATA": "C:/Users/example/AppData/Local"}),
        ):
            self.assertEqual(
                app_data_dir(),
                Path("C:/Users/example/AppData/Local/Ledgerly"),
            )
            self.assertEqual(import_archive_dir(), app_data_dir() / "imported_statements")

    def test_prepare_app_data_dir_creates_the_current_storage_location(self):
        target = Path("C:/example/Ledgerly")
        with (
            patch("app.core.paths.app_data_dir", return_value=target),
            patch.object(Path, "mkdir") as mkdir,
        ):
            result = prepare_app_data_dir()

        self.assertEqual(result, target)
        mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_linux_build_uses_xdg_data_home(self):
        absolute_data_home = Path(Path.cwd().anchor) / "example-data"
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "platform", "linux"),
            patch.dict(os.environ, {"XDG_DATA_HOME": str(absolute_data_home)}),
        ):
            self.assertEqual(app_data_dir(), absolute_data_home / "ledgerly")

    def test_linux_build_ignores_relative_xdg_data_home(self):
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "platform", "linux"),
            patch.dict(os.environ, {"XDG_DATA_HOME": "relative-data"}),
            patch.object(Path, "home", return_value=Path("/home/example")),
        ):
            self.assertEqual(app_data_dir(), Path("/home/example/.local/share/ledgerly"))


if __name__ == "__main__":
    unittest.main()
