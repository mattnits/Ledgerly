from pathlib import Path
import re

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import COLORS, awesome_icon, set_delete_button_icon, set_label_icon
from app.utils.constants import SUPPORTED_PARSE_TYPES


def infer_parse_type_from_filename(
    filename: str,
) -> SUPPORTED_PARSE_TYPES | None:
    """Infer the statement type from whole words in the selected file name."""
    words = set(re.findall(r"[a-z0-9]+", Path(filename).stem.casefold()))
    if "amex" in words or {"american", "express"}.issubset(words):
        return SUPPORTED_PARSE_TYPES.AMEX
    if "td" in words:
        if "debit" in words:
            return SUPPORTED_PARSE_TYPES.TD_DEBIT
        if words.intersection({"credit", "visa", "mastercard"}):
            return SUPPORTED_PARSE_TYPES.TD_CREDIT
        return SUPPORTED_PARSE_TYPES.TD_DEBIT
    return None


def _format_file_size(filename: str) -> str:
    try:
        size = Path(filename).stat().st_size
    except OSError:
        return "Size unavailable"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


class FileRow(QFrame):
    remove_requested = Signal(str)
    parser_changed = Signal(str)

    def __init__(self, filename: str, parent=None):
        super().__init__(parent)
        self.filename = filename
        self.error_message: str | None = None
        self.setObjectName("statementFileRow")
        self.setProperty("failed", False)
        self.setMinimumHeight(86)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 14, 12)
        layout.setSpacing(8)

        self.file_icon = QLabel()
        set_label_icon(self.file_icon, "fa6s.file-lines", color="#aebed4", size=26)
        layout.addWidget(self.file_icon)

        file_details = QVBoxLayout()
        file_details.setSpacing(3)
        self.filename_label = QLabel(Path(filename).name)
        self.filename_label.setObjectName("statementFilename")
        self.filename_label.setToolTip(filename)
        self.size_label = QLabel(_format_file_size(filename))
        self.size_label.setObjectName("statementFileMeta")
        file_details.addWidget(self.filename_label)
        file_details.addWidget(self.size_label)
        layout.addLayout(file_details, 3)

        status = QWidget()
        status.setMinimumWidth(170)
        status.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        status_layout = QVBoxLayout(status)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(3)
        status_heading = QHBoxLayout()
        status_heading.setContentsMargins(0, 0, 0, 0)
        status_heading.setSpacing(8)
        self.error_icon = QLabel()
        self.status_label = QLabel()
        status_heading.addWidget(self.error_icon)
        status_heading.addWidget(self.status_label)
        status_heading.addStretch()
        self.status_detail = QLabel()
        self.status_detail.setObjectName("statementStatusDetail")
        self.status_detail.setWordWrap(True)
        self.status_detail.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        status_layout.addLayout(status_heading)
        status_layout.addWidget(self.status_detail)
        layout.addWidget(status, 2)

        self.parse_type = QComboBox()
        self.parse_type.setObjectName("statementTypeCombo")
        self.parse_type.addItems(SUPPORTED_PARSE_TYPES)
        self.parse_type.setFixedWidth(174)
        inferred_type = infer_parse_type_from_filename(filename)
        if inferred_type is not None:
            self.parse_type.setCurrentText(inferred_type.value)
        self.parse_type.currentTextChanged.connect(self.parser_changed.emit)
        layout.addWidget(self.parse_type)

        self.remove_button = QPushButton()
        self.remove_button.setObjectName("statementRemoveButton")
        self.remove_button.setFixedSize(40, 40)
        self.remove_button.setToolTip("Remove from import queue")
        self.remove_button.setAccessibleName(
            f"Remove {Path(filename).name} from import queue"
        )
        set_delete_button_icon(self.remove_button, size=17)
        self.remove_button.clicked.connect(
            lambda: self.remove_requested.emit(self.filename)
        )
        layout.addWidget(self.remove_button)

        self.set_error(None)

    def get_parse_type(self) -> str:
        return self.parse_type.currentText()

    def set_error(self, message: str | None) -> None:
        self.error_message = message or None
        failed = self.error_message is not None
        self.setProperty("failed", failed)
        self.status_label.setText("Failed" if failed else "Ready")
        self.status_label.setObjectName(
            "statementStatusFailed" if failed else "statementStatusReady"
        )
        self.status_detail.setText(self.error_message or "Ready to import")
        self.status_detail.setToolTip(self.error_message or "")
        set_label_icon(
            self.error_icon,
            "fa6s.circle-exclamation" if failed else "fa6s.circle-check",
            color=COLORS["negative"] if failed else COLORS["positive"],
            size=16,
        )
        self.file_icon.setPixmap(
            awesome_icon(
                "fa6s.file-lines",
                color=COLORS["negative"] if failed else "#aebed4",
            ).pixmap(26, 26)
        )
        self.style().unpolish(self)
        self.style().polish(self)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.update()
