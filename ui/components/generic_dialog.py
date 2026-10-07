from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import COLORS, awesome_icon, set_button_icon


class GenericDialog(QDialog):
    """Shared frameless modal shell used by forms throughout the application."""

    submitted = Signal()

    def __init__(
        self,
        title: str,
        content: QWidget,
        parent=None,
        *,
        submit_label: str = "Submit",
        subtitle: str | None = None,
        icon_name: str = "fa6s.pen-to-square",
        info_text: str | None = None,
    ):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setModal(True)
        self.setObjectName("genericDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.setMinimumSize(500, 340)
        self.resize(620, 440)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        self.card = QFrame()
        self.card.setObjectName("dialogCard")
        outer.addWidget(self.card)
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 165))
        self.card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(0)

        self.header_widget = QWidget()
        self.header_widget.setObjectName("dialogHeader")
        header = QHBoxLayout(self.header_widget)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(16)

        self.icon_frame = QFrame()
        self.icon_frame.setObjectName("dialogIconFrame")
        self.icon_frame.setFixedSize(56, 56)
        icon_layout = QVBoxLayout(self.icon_frame)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(awesome_icon(icon_name, color="#56a9ff").pixmap(29, 29))
        icon_layout.addWidget(icon)
        header.addWidget(self.icon_frame, alignment=Qt.AlignmentFlag.AlignTop)

        heading = QVBoxLayout()
        heading.setSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("dialogTitle")
        heading.addWidget(self.title_label)
        self.subtitle_label = QLabel(subtitle or "")
        self.subtitle_label.setObjectName("dialogSubtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(subtitle))
        heading.addWidget(self.subtitle_label)
        header.addLayout(heading, 1)

        self.close_button = QToolButton()
        self.close_button.setObjectName("dialogCloseButton")
        self.close_button.setFixedSize(34, 34)
        self.close_button.setToolTip("Close")
        self.close_button.setAccessibleName(f"Close {title}")
        set_button_icon(
            self.close_button,
            "fa6s.xmark",
            color=COLORS["text_muted"],
            active_color=COLORS["text"],
            size=18,
        )
        self.close_button.clicked.connect(self.reject)
        header.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.header_widget)
        layout.addSpacing(24)

        self.content = content
        if not self.content.objectName():
            self.content.setObjectName("dialogContent")
        self.content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self.content, 1)

        self.info_panel: QFrame | None = None
        if info_text:
            layout.addSpacing(18)
            self.info_panel = QFrame()
            self.info_panel.setObjectName("dialogInfoPanel")
            info_layout = QHBoxLayout(self.info_panel)
            info_layout.setContentsMargins(16, 13, 16, 13)
            info_layout.setSpacing(13)
            info_icon = QLabel()
            info_icon.setPixmap(
                awesome_icon("fa6s.circle-info", color="#4da3ff").pixmap(20, 20)
            )
            info_icon.setFixedSize(24, 24)
            info_label = QLabel(info_text)
            info_label.setObjectName("dialogInfoText")
            info_label.setWordWrap(True)
            info_layout.addWidget(info_icon, alignment=Qt.AlignmentFlag.AlignTop)
            info_layout.addWidget(info_label, 1)
            layout.addWidget(self.info_panel)

        layout.addSpacing(20)
        divider = QFrame()
        divider.setObjectName("dialogFooterDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(divider)
        layout.addSpacing(16)

        self.footer_widget = QWidget()
        self.footer_widget.setObjectName("dialogFooter")
        button_layout = QHBoxLayout(self.footer_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(12)
        button_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("dialogCancelButton")
        self.cancel_button.setMinimumSize(104, 42)
        self.submit_button = QPushButton(submit_label)
        self.submit_button.setObjectName("primaryButton")
        self.submit_button.setMinimumSize(132, 42)
        self.submit_button.setDefault(True)
        set_button_icon(
            self.submit_button,
            "fa6s.check",
            color="#ffffff",
            active_color="#ffffff",
            size=15,
        )

        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.submit_button)
        layout.addWidget(self.footer_widget)

        self.cancel_button.clicked.connect(self.reject)
        self.submit_button.clicked.connect(self._submit)

    def _submit(self) -> None:
        self.submitted.emit()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API spelling
        super().showEvent(event)
        self._center_on_parent()

    def _center_on_parent(self) -> None:
        parent = self.parentWidget()
        target = (
            parent.window().frameGeometry()
            if parent is not None
            else self.screen().availableGeometry()
        )
        frame = self.frameGeometry()
        frame.moveCenter(target.center())
        available = self.screen().availableGeometry()
        x = max(
            available.left(),
            min(frame.left(), available.right() - frame.width() + 1),
        )
        y = max(
            available.top(),
            min(frame.top(), available.bottom() - frame.height() + 1),
        )
        self.move(x, y)
