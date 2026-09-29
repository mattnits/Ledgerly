from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ui.theme import brand_icon


class AccountBadge(QWidget):
    """Compact, reusable account identity used by tables across the app."""

    def __init__(
        self,
        account_name: str,
        institution: str,
        *,
        icon_size: int = 24,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("tableCell")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(7)

        icon_label = QLabel()
        icon_label.setObjectName("accountBrandIcon")
        icon_label.setPixmap(brand_icon(institution, size=icon_size).pixmap(icon_size, icon_size))
        icon_label.setFixedSize(icon_size, icon_size)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        self.name_label = QLabel(account_name)
        self.name_label.setObjectName("accountName")
        self.name_label.setMinimumWidth(
            self.name_label.fontMetrics().horizontalAdvance(account_name) + 4
        )
        self.name_label.setToolTip(f"{account_name} · {institution}")
        layout.addWidget(self.name_label, 1)

