import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui.dashboard import DashboardPage
from utils.import_archive import stage_import_files


class ImportArchiveTest(unittest.TestCase):
    def test_selected_files_are_staged_as_one_batch(self):
        root = Path("archive-root")
        with (
            patch.object(Path, "resolve", autospec=True, side_effect=lambda path, strict: path),
            patch.object(Path, "is_file", return_value=True),
            patch.object(Path, "mkdir") as mkdir,
            patch("utils.import_archive.shutil.copy2") as copy,
        ):
            archive = stage_import_files(
                ["first.csv", "second.csv"],
                destination_root=root,
            )

        self.assertEqual(mkdir.call_args_list[0], call(parents=True, exist_ok=True))
        self.assertEqual(copy.call_count, 2)
        self.assertEqual(archive.staging_path.parent, root)
        self.assertEqual(archive.final_path.parent, root)

    def test_failed_batch_copy_discards_every_staged_file(self):
        with (
            patch.object(Path, "resolve", autospec=True, side_effect=lambda path, strict: path),
            patch.object(Path, "is_file", return_value=True),
            patch.object(Path, "mkdir"),
            patch.object(Path, "exists", return_value=True),
            patch("utils.import_archive.shutil.copy2", side_effect=OSError("full")),
            patch("utils.import_archive.shutil.rmtree") as remove_tree,
        ):
            with self.assertRaisesRegex(OSError, "full"):
                stage_import_files(["first.csv"])

        remove_tree.assert_called_once()

    def test_dashboard_commits_archive_only_after_every_parser_succeeds(self):
        archive = MagicMock()
        parser = MagicMock()
        parser.get_results.return_value = []
        dialog = MagicMock()
        dialog.get_file_parse_types.return_value = [("first.csv", "TD Debit")]
        dialog.get_files.return_value = ["first.csv"]
        dialog.get_date_range.return_value = (None, None)
        dialog.should_save_source_files.return_value = True
        window = SimpleNamespace(
            transactions_page=SimpleNamespace(reload=MagicMock())
        )
        page = SimpleNamespace(
            user_id="user-1",
            files_to_parse=[],
            window=lambda: window,
            reload=MagicMock(),
        )

        with (
            patch("ui.dashboard.stage_import_files", return_value=archive) as stage,
            patch("ui.dashboard.GenericParser", return_value=parser),
        ):
            DashboardPage._parse_selected_files(page, dialog)

        stage.assert_called_once_with(["first.csv"])
        archive.commit.assert_called_once_with()
        archive.discard.assert_not_called()
        dialog.accept.assert_called_once_with()

    def test_failed_import_discards_the_whole_archive_batch(self):
        archive = MagicMock()
        parser = MagicMock()
        errors = [("second.csv", "Invalid columns")]
        parser.get_results.return_value = errors
        dialog = MagicMock()
        dialog.get_file_parse_types.return_value = [
            ("first.csv", "TD Debit"),
            ("second.csv", "TD Debit"),
        ]
        dialog.get_files.return_value = ["first.csv", "second.csv"]
        dialog.get_date_range.return_value = (None, None)
        dialog.should_save_source_files.return_value = True
        page = SimpleNamespace(user_id="user-1")

        with (
            patch("ui.dashboard.stage_import_files", return_value=archive),
            patch("ui.dashboard.GenericParser", return_value=parser),
        ):
            DashboardPage._parse_selected_files(page, dialog)

        archive.discard.assert_called_once_with()
        archive.commit.assert_not_called()
        dialog.show_errors.assert_called_once_with(errors)


if __name__ == "__main__":
    unittest.main()
