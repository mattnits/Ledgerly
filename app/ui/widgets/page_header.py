from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_SUBTITLE_PLACEHOLDER = "Subtitle"


class PageHeader(QWidget):
    def __init__(
        self,
        title: str,
        subtitle: str | None = None,
        action_button: QPushButton | None = None,
        centered: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)

        heading = QVBoxLayout()
        heading.setSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("pageTitle")
        heading.addWidget(self.title_label)

        # Keep the subtitle row even when there is no subtitle so headers (and
        # especially their action buttons) stay aligned from page to page.
        self.subtitle_label = QLabel(subtitle or _SUBTITLE_PLACEHOLDER)
        self.subtitle_label.setObjectName("pageSubtitle")
        self.subtitle_label.setWordWrap(True)
        if not subtitle:
            policy = self.subtitle_label.sizePolicy()
            policy.setRetainSizeWhenHidden(True)
            self.subtitle_label.setSizePolicy(policy)
            self.subtitle_label.hide()
        heading.addWidget(self.subtitle_label)

        if centered:
            self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            layout.addLayout(heading, 1)

        if centered:
            layout.addStretch()
            layout.addLayout(heading)
            layout.addStretch()

        if action_button is not None:
            layout.addWidget(action_button, alignment=Qt.AlignmentFlag.AlignVCenter)

    def set_subtitle(self, subtitle: str) -> None:
        self.subtitle_label.setText(subtitle or _SUBTITLE_PLACEHOLDER)
        self.subtitle_label.setVisible(bool(subtitle))
