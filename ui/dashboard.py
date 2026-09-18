from PySide6.QtWidgets import (
    QPushButton,
    QWidget,
    QVBoxLayout,
)

from parsers.generic_parser import GenericParser
from ui.components.page_header import PageHeader
from ui.components.file_upload_dialog import FileUploadDialog
from utils.constants import ADD_STATMENT_LABEL


class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            32,
            32,
            32,
            32,
        )

        self.files_to_parse = []
        add_files_button = QPushButton(ADD_STATMENT_LABEL)
        add_files_button.clicked.connect(self.open_file_selection)
        layout.addWidget(PageHeader("Dashboard", action_button=add_files_button))

        layout.addStretch()

    def open_file_selection(self):
        dialog = FileUploadDialog(self.window())
        dialog.submitted.connect(lambda: self._parse_selected_files(dialog))
        dialog.exec()

    def _parse_selected_files(self, dialog: FileUploadDialog) -> None:
        file_data = dialog.get_file_parse_types()
        if not file_data:
            dialog.file_selection.label.setText("Select at least one file")
            return

        parser = GenericParser(file_data, self.window().sidebar.current_user_id)
        parser.parse()
        errors = parser.get_results()

        if errors:
            dialog.show_errors(errors)
            return

        self.files_to_parse = dialog.get_files()
        self.window().transactions_page.reload()
        dialog.accept()
