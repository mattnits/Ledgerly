from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.components.date_picker import DatePickerEdit
from ui.components.file_row import FileRow
from ui.components.toggle_switch import ToggleSwitch
from ui.preferences import save_imported_files_enabled
from ui.theme import COLORS, set_button_icon, set_label_icon
from utils.app_paths import import_archive_label


def previous_month_bounds(reference: date) -> tuple[date, date]:
    first_of_this_month = date(reference.year, reference.month, 1)
    last_of_previous_month = first_of_this_month - timedelta(days=1)
    first_of_previous_month = date(
        last_of_previous_month.year,
        last_of_previous_month.month,
        1,
    )
    return first_of_previous_month, last_of_previous_month


class ErrorSummary(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statementErrorSummary")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(8)
        self.icon = QLabel()
        set_label_icon(
            self.icon, "fa6s.circle-exclamation", color=COLORS["negative"], size=20
        )
        layout.addWidget(self.icon, alignment=Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(3)
        self.title = QLabel()
        self.title.setObjectName("statementErrorTitle")
        self.detail = QLabel()
        self.detail.setObjectName("statementErrorDetail")
        self.detail.setWordWrap(True)
        self.detail.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        text.addWidget(self.title)
        text.addWidget(self.detail)
        layout.addLayout(text, 1)
        self.hide()

    def show_file_errors(self, messages: list[str]) -> None:
        if not messages:
            self.hide()
            return
        count = len(messages)
        self.title.setText(
            f"{count} file{'s' if count != 1 else ''} failed to import"
        )
        detail = messages[0]
        if count > 1:
            detail = f"{detail}  (+{count - 1} more)"
        self.detail.setText(detail)
        self.show()

    def show_message(self, title: str, detail: str) -> None:
        self.title.setText(title)
        self.detail.setText(detail)
        self.show()


class FilePickerPanel(QFrame):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statementFilePicker")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(112)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 17, 18, 17)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.button = QPushButton("Choose CSV files")
        self.button.setObjectName("statementChooseFilesButton")
        set_button_icon(self.button, "fa6s.file-circle-plus", size=20)
        self.help_label = QLabel("You can select multiple files at once.")
        self.help_label.setObjectName("statementFilePickerHelp")
        self.help_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.button, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.help_label)
        self.button.clicked.connect(self.clicked.emit)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class FileSelection(QWidget):
    queue_changed = Signal(bool)

    def __init__(self, parent=None, *, save_import_default: bool | None = None):
        super().__init__(parent)
        self.selected_files: list[str] = []
        self.file_rows: list[FileRow] = []
        self._errors: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        # Retained for compatibility with existing callers; visible errors use
        # the styled summary card instead of an unstructured label.
        self.label = QLabel("No files selected")
        self.label.hide()

        self.error_summary = ErrorSummary()
        layout.addWidget(self.error_summary)

        self.file_list = QScrollArea()
        self.file_list.setObjectName("statementFileList")
        self.file_list.setWidgetResizable(True)
        self.file_list.setFrameShape(QFrame.Shape.NoFrame)
        self.file_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.file_list.setMinimumHeight(150)
        self.file_rows_widget = QWidget()
        self.file_rows_widget.setObjectName("statementFileRows")
        self.file_rows_layout = QVBoxLayout(self.file_rows_widget)
        self.file_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.file_rows_layout.setSpacing(1)
        self.file_rows_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.empty_state = QWidget()
        self.empty_state.setObjectName("statementEmptyState")
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(20, 24, 20, 24)
        empty_layout.setSpacing(7)
        empty_layout.addStretch()
        empty_icon = QLabel()
        set_label_icon(
            empty_icon, "fa6s.folder-open", color=COLORS["text_dim"], size=25
        )
        empty_layout.addWidget(empty_icon, alignment=Qt.AlignmentFlag.AlignCenter)
        self.empty_title = QLabel("No statement files selected")
        self.empty_title.setObjectName("statementEmptyTitle")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_detail = QLabel(
            "Choose one or more files below to add them to the import queue."
        )
        self.empty_detail.setObjectName("statementEmptyDetail")
        self.empty_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_detail.setWordWrap(True)
        empty_layout.addWidget(self.empty_title)
        empty_layout.addWidget(self.empty_detail)
        empty_layout.addStretch()
        self.file_rows_layout.addWidget(self.empty_state, 1)
        self.file_list.setWidget(self.file_rows_widget)
        layout.addWidget(self.file_list, 1)

        self.date_range_card = QFrame()
        self.date_range_card.setObjectName("statementDateRange")
        date_layout = QVBoxLayout(self.date_range_card)
        date_layout.setContentsMargins(14, 12, 14, 12)
        date_layout.setSpacing(10)
        self.limit_date_range = QCheckBox(
            "Only import transactions in a date range"
        )
        self.limit_date_range.setToolTip(
            "Transactions outside the selected dates will be ignored."
        )
        date_layout.addWidget(self.limit_date_range)

        start_default, end_default = previous_month_bounds(date.today())
        self.start_date = DatePickerEdit(QDate(
            start_default.year, start_default.month, start_default.day
        ))
        self.end_date = DatePickerEdit(QDate(
            end_default.year, end_default.month, end_default.day
        ))
        for editor in (self.start_date, self.end_date):
            editor.setEnabled(False)
            editor.setFixedWidth(190)

        date_range_row = QHBoxLayout()
        date_range_row.setSpacing(10)
        date_range_row.addWidget(QLabel("From"))
        date_range_row.addWidget(self.start_date)
        date_range_row.addSpacing(12)
        date_range_row.addWidget(QLabel("To"))
        date_range_row.addWidget(self.end_date)
        date_range_row.addStretch()
        date_layout.addLayout(date_range_row)
        layout.addWidget(self.date_range_card)

        self.storage_card = QFrame()
        self.storage_card.setObjectName("statementStorageOption")
        storage_layout = QHBoxLayout(self.storage_card)
        storage_layout.setContentsMargins(14, 11, 14, 11)
        storage_layout.setSpacing(14)
        storage_copy = QVBoxLayout()
        storage_copy.setSpacing(2)
        storage_title = QLabel("Save source files")
        storage_title.setObjectName("statementStorageTitle")
        storage_description = QLabel(
            "Save all selected statements to "
            f"{import_archive_label()} after a successful import."
        )
        storage_description.setObjectName("statementStorageDescription")
        storage_description.setWordWrap(True)
        storage_copy.addWidget(storage_title)
        storage_copy.addWidget(storage_description)
        storage_layout.addLayout(storage_copy, 1)
        self.save_files_toggle = ToggleSwitch()
        self.save_files_toggle.setObjectName("statementSaveFilesToggle")
        self.save_files_toggle.setAccessibleName("Save all imported source files")
        self.save_files_toggle.setToolTip(
            "Applies to every file in this import and does not change Settings"
        )
        default = (
            save_imported_files_enabled()
            if save_import_default is None
            else save_import_default
        )
        self.save_files_toggle.setChecked(default)
        storage_layout.addWidget(
            self.save_files_toggle,
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )
        layout.addWidget(self.storage_card)

        self.file_picker = FilePickerPanel()
        self.select_button = self.file_picker.button
        self.file_picker.clicked.connect(self.select_files)
        layout.addWidget(self.file_picker)

        self.limit_date_range.toggled.connect(self.start_date.setEnabled)
        self.limit_date_range.toggled.connect(self.end_date.setEnabled)
        self.setStyleSheet(self._stylesheet())

    def select_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select transaction files",
            "",
            "Data Files (*.csv *.xlsx *.xls);;All Files (*)",
        )
        if files:
            self.set_files(files)

    def set_files(self, files: list[str]) -> None:
        self._clear_rows()
        self.selected_files = list(dict.fromkeys(files))
        self._errors.clear()
        self.error_summary.hide()
        for filename in self.selected_files:
            row = FileRow(filename)
            row.remove_requested.connect(self.remove_file)
            row.parser_changed.connect(
                lambda _value, selected=row: self._parser_changed(selected)
            )
            self.file_rows_layout.addWidget(row)
            self.file_rows.append(row)
        self.empty_state.setVisible(not self.file_rows)
        self.label.setText(f"{len(self.selected_files)} file(s) selected")
        self.queue_changed.emit(bool(self.file_rows))

    def remove_file(self, filename: str) -> None:
        row = next(
            (item for item in self.file_rows if item.filename == filename), None
        )
        if row is None:
            return
        self.file_rows.remove(row)
        self.selected_files = [
            selected for selected in self.selected_files if selected != filename
        ]
        self._errors.pop(filename, None)
        self.file_rows_layout.removeWidget(row)
        row.deleteLater()
        self.empty_state.setVisible(not self.file_rows)
        self.label.setText(
            f"{len(self.selected_files)} file(s) selected"
            if self.selected_files
            else "No files selected"
        )
        self._refresh_error_summary()
        self.queue_changed.emit(bool(self.file_rows))

    def get_files(self) -> list[str]:
        return list(self.selected_files)

    def get_file_parse_types(self) -> list[tuple[str, str]]:
        return [(row.filename, row.get_parse_type()) for row in self.file_rows]

    def get_date_range(self) -> tuple[date | None, date | None]:
        if not self.limit_date_range.isChecked():
            return None, None
        start = self.start_date.date().toPython()
        end = self.end_date.date().toPython()
        if start > end:
            raise ValueError("The import start date must be on or before the end date")
        return start, end

    def should_save_source_files(self) -> bool:
        return self.save_files_toggle.isChecked()

    def show_errors(self, errors: list[tuple[str, str]]) -> None:
        selected = set(self.selected_files)
        self._errors = {
            filename: message
            for filename, message in errors
            if filename in selected
        }
        for row in self.file_rows:
            row.set_error(self._errors.get(row.filename))
        self._refresh_error_summary()

    def show_general_error(self, message: str) -> None:
        self.label.setText(message)
        self.error_summary.show_message("Unable to import", message)

    def _parser_changed(self, row: FileRow) -> None:
        if row.filename not in self._errors:
            return
        self._errors.pop(row.filename, None)
        row.set_error(None)
        self._refresh_error_summary()

    def _refresh_error_summary(self) -> None:
        messages = [
            self._errors[row.filename]
            for row in self.file_rows
            if row.filename in self._errors
        ]
        self.error_summary.show_file_errors(messages)

    def _clear_rows(self) -> None:
        for row in self.file_rows:
            self.file_rows_layout.removeWidget(row)
            row.deleteLater()
        self.file_rows = []

    @staticmethod
    def _stylesheet() -> str:
        return f"""
            QFrame#statementErrorSummary {{
                background: #2a191d;
                border: 1px solid #63303a;
                border-radius: 11px;
            }}
            QLabel#statementErrorTitle {{
                color: #ffd8da;
                font-size: 13px;
                font-weight: 700;
            }}
            QLabel#statementErrorDetail {{ color: #c9aeb3; }}
            QScrollArea#statementFileList,
            QWidget#statementFileRows {{
                background: {COLORS['surface']};
                border: none;
            }}
            QScrollArea#statementFileList {{
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
            QFrame#statementFileRow {{
                background: {COLORS['surface']};
                border: none;
                border-bottom: 1px solid {COLORS['border_soft']};
            }}
            QFrame#statementFileRow[failed="true"] {{
                background: #24191d;
                border-left: 2px solid {COLORS['negative']};
                border-bottom: 1px solid #4b2931;
            }}
            QLabel#statementFilename {{
                color: {COLORS['text']};
                font-size: 13px;
                font-weight: 600;
            }}
            QLabel#statementFileMeta,
            QLabel#statementStatusDetail,
            QLabel#statementFilePickerHelp,
            QLabel#statementEmptyDetail {{
                color: {COLORS['text_dim']};
                font-size: 11px;
            }}
            QLabel#statementEmptyTitle {{
                color: {COLORS['text_muted']};
                font-size: 13px;
                font-weight: 650;
            }}
            QLabel#statementStatusReady {{ color: {COLORS['positive']}; }}
            QLabel#statementStatusFailed {{ color: {COLORS['negative']}; }}
            QComboBox#statementTypeCombo {{
                background: {COLORS['surface_alt']};
                border-color: {COLORS['border']};
                min-height: 24px;
            }}
            QPushButton#statementRemoveButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 9px;
                padding: 0;
            }}
            QPushButton#statementRemoveButton:hover {{
                background: #311b22;
                border-color: #713543;
            }}
            QFrame#statementDateRange {{
                background: transparent;
                border: none;
            }}
            QFrame#statementStorageOption {{
                background: #12171d;
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
            }}
            QLabel#statementStorageTitle {{
                color: {COLORS['text']};
                font-size: 13px;
                font-weight: 650;
            }}
            QLabel#statementStorageDescription {{
                color: {COLORS['text_dim']};
                font-size: 11px;
            }}
            QFrame#statementFilePicker {{
                background: #12171d;
                border: 1px dashed #3b5068;
                border-radius: 12px;
            }}
            QFrame#statementFilePicker:hover {{
                background: #151c24;
                border-color: #52749a;
            }}
            QPushButton#statementChooseFilesButton {{
                background: transparent;
                border: none;
                color: {COLORS['text']};
                font-size: 14px;
                font-weight: 650;
                padding: 4px 10px;
            }}
        """
