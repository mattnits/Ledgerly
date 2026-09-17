from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
)

from ui.components.file_row import FileRow


class FileSelection(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.selected_files = []
        self.file_rows = []

        layout = QVBoxLayout(self)

        self.label = QLabel("No files selected")
        self.select_button = QPushButton("Choose Files")

        self.file_rows_layout = QVBoxLayout()

        layout.addWidget(self.label)
        layout.addLayout(self.file_rows_layout)
        layout.addWidget(self.select_button)

        self.select_button.clicked.connect(self.select_files)

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select transaction files",
            "",
            "Data Files (*.csv *.xlsx *.xls);;All Files (*)"
        )

        if files:
            self.selected_files = files
            self.label.setText(
                f"{len(files)} file(s) selected"
            )
            for row in self.file_rows:
                self.file_rows_layout.removeWidget(row)
                row.deleteLater()

            self.file_rows = []
            for filename in self.selected_files:
                row = FileRow(filename)
                self.file_rows_layout.addWidget(row)
                self.file_rows.append(row)

    def get_files(self):
        return self.selected_files

    def get_file_parse_types(self) -> list[tuple[str, str]]:
        return [(row.filename, row.get_parse_type()) for row in self.file_rows]

    def show_errors(self, errors: list[tuple[str, str]]) -> None:
        messages = dict(errors)
        for row in self.file_rows:
            row.set_error(messages.get(row.filename))
        if errors:
            self.label.setText(f"{len(errors)} file(s) failed: {errors[0][1]}")
