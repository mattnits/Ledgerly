from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from app.ui.theme import brand_icon, icon_pixmap


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
        layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setObjectName("accountBrandIcon")
        icon_label.setPixmap(
            icon_pixmap(brand_icon(institution, size=icon_size), icon_size, icon_size)
        )
        icon_label.setFixedSize(icon_size, icon_size)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        self.name_label = QLabel(account_name)
        self.name_label.setObjectName("accountName")
        self.name_label.setMinimumWidth(0)
        self.name_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.name_label.setToolTip(f"{account_name} · {institution}")
        layout.addWidget(self.name_label, 1)

