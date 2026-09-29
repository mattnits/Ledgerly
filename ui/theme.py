from __future__ import annotations

from pathlib import Path

import qtawesome as qta
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication, QAbstractButton, QLabel


APP_ROOT = Path(__file__).resolve().parent.parent
ICON_ROOT = APP_ROOT / "icons"

COLORS = {
    "canvas": "#0d0f12",
    "sidebar": "#101318",
    "surface": "#171b20",
    "surface_alt": "#1d2229",
    "surface_hover": "#262c34",
    "border": "#303740",
    "border_soft": "#252b32",
    "text": "#f2f4f7",
    "text_muted": "#a7afb9",
    "text_dim": "#737b85",
    "primary": "#1677ff",
    "primary_hover": "#2a86ff",
    "primary_pressed": "#0f62db",
    "positive": "#18d98b",
    "negative": "#ff4d4f",
    "warning": "#ffbd4a",
}


_qtawesome_available: bool | None = None


def awesome_icon(
    name: str,
    *,
    color: str = COLORS["text_muted"],
    active_color: str = COLORS["text"],
) -> QIcon:
    """Return a consistently styled QtAwesome icon without risking UI startup."""
    global _qtawesome_available
    if _qtawesome_available is False:
        return QIcon()
    try:
        icon = qta.icon(
            name,
            color=color,
            color_active=active_color,
            color_selected=active_color,
            color_on=COLORS["primary"],
        )
    except Exception:
        # QtAwesome may be unable to register its bundled font on a locked-down
        # Windows profile. Keep the application usable even in that case.
        _qtawesome_available = False
        return QIcon()
    _qtawesome_available = True
    return icon


def set_button_icon(
    button: QAbstractButton,
    name: str,
    *,
    color: str = COLORS["text_muted"],
    active_color: str = COLORS["text"],
    size: int = 18,
) -> None:
    button.setIcon(awesome_icon(name, color=color, active_color=active_color))
    button.setIconSize(QSize(size, size))


def set_label_icon(
    label: QLabel,
    name: str,
    *,
    color: str = COLORS["text_muted"],
    size: int = 18,
) -> None:
    label.setPixmap(awesome_icon(name, color=color).pixmap(size, size))
    label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)


def brand_icon(institution: str, *, size: int = 24) -> QIcon:
    """Return the supplied TD/Amex artwork, with a neutral bank fallback."""
    normalized = institution.casefold()
    if "american express" in normalized or "amex" in normalized:
        path = ICON_ROOT / "amex_icon.png"
        crop_td = False
    elif normalized == "td" or "toronto-dominion" in normalized:
        path = ICON_ROOT / "td_icon.jpg"
        crop_td = True
    else:
        return awesome_icon("fa6s.building-columns", color="#b2b8c1")

    source = QPixmap(str(path))
    if source.isNull():
        return awesome_icon("fa6s.building-columns", color="#b2b8c1")
    if crop_td:
        source = source.copy(
            int(source.width() * 0.07),
            int(source.height() * 0.09),
            int(source.width() * 0.86),
            int(source.height() * 0.80),
        )

    target = QPixmap(size, size)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, size, size), 5, 5)
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, size, size, source)
    painter.end()
    return QIcon(target)


TRANSACTION_TYPE_ICONS = {
    "EXPENSE": "fa6s.credit-card",
    "INCOME": "fa6s.briefcase",
    "E_TRANSFER": "fa6s.right-left",
    "TRANSFER": "fa6s.money-bill-transfer",
    "CREDIT_CARD_PAYMENT": "fa6s.file-invoice-dollar",
    "REFUND_REIMBURSEMENT": "fa6s.rotate-left",
    "SAVINGS": "fa6s.piggy-bank",
    "INVESTMENT": "fa6s.arrow-trend-up",
}


def transaction_type_icon(transaction_type, *, color: str = "#b2b8c1") -> QIcon:
    value = getattr(transaction_type, "value", transaction_type)
    name = TRANSACTION_TYPE_ICONS.get(value, "fa6s.circle-question")
    return awesome_icon(name, color=color)


def category_icon_name(name: str | None) -> str:
    normalized = (name or "").casefold()
    mappings = (
        (("food", "restaurant"), "fa6s.utensils"),
        (("grocer",), "fa6s.cart-shopping"),
        (("housing", "rent", "home"), "fa6s.house-chimney"),
        (("bill", "utilit", "subscription"), "fa6s.file-invoice-dollar"),
        (("transport", "travel"), "fa6s.car"),
        (("entertain",), "fa6s.film"),
        (("shopping",), "fa6s.bag-shopping"),
        (("health", "fitness"), "fa6s.dumbbell"),
        (("gift",), "fa6s.gift"),
        (("salary", "income"), "fa6s.briefcase"),
    )
    for terms, icon_name in mappings:
        if any(term in normalized for term in terms):
            return icon_name
    return "fa6s.tag"


def contrasting_text(background: str) -> str:
    color = QColor(background)
    channels = (color.redF(), color.greenF(), color.blueF())
    linear = tuple(
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    )
    luminance = sum(
        weight * channel
        for weight, channel in zip((0.2126, 0.7152, 0.0722), linear)
    )
    return "#09111d" if luminance > 0.35 else "#f7fbff"


APP_STYLESHEET = f"""
QWidget {{
    color: {COLORS['text']};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}}
QMainWindow, QWidget#appRoot, QStackedWidget#pageStack,
QWidget#dashboardPage, QWidget#transactionsPage, QWidget#accountsPage,
QWidget#categoriesPage, QWidget#settingsPage, QWidget#welcomePage,
QWidget#addUserPage {{
    background: {COLORS['canvas']};
}}
QToolTip {{
    color: {COLORS['text']};
    background: {COLORS['surface_alt']};
    border: 1px solid {COLORS['border']};
    padding: 6px 8px;
}}
QLabel#pageTitle {{
    color: {COLORS['text']};
    font-size: 32px;
    font-weight: 750;
}}
QLabel#pageSubtitle, QLabel#mutedLabel, QLabel#emptyLabel {{
    color: {COLORS['text_muted']};
    font-size: 14px;
}}
QLabel#dialogTitle {{
    color: {COLORS['text']};
    font-size: 20px;
    font-weight: 700;
}}
QLabel#sectionTitle {{
    color: {COLORS['text']};
    font-size: 15px;
    font-weight: 650;
}}
QLabel#accountName {{ color: #dfe2e6; }}
QWidget#tableCell {{ background: transparent; }}
QPushButton {{
    color: #dde1e6;
    background: {COLORS['surface_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 9px;
    min-height: 20px;
    padding: 9px 14px;
}}
QPushButton:hover {{
    color: #ffffff;
    background: {COLORS['surface_hover']};
    border-color: #4a515b;
}}
QPushButton:pressed {{ background: #15181d; }}
QPushButton:disabled {{ color: #656b73; background: #181b20; }}
QPushButton#primaryButton, QPushButton#pageActionButton {{
    color: #ffffff;
    background: {COLORS['primary']};
    border-color: #2784ff;
    font-weight: 600;
    padding: 10px 18px;
}}
QPushButton#primaryButton:hover, QPushButton#pageActionButton:hover {{
    background: {COLORS['primary_hover']};
}}
QPushButton#secondaryActionButton {{
    color: #e3e5e8;
    background: #1e2228;
    border-color: #373d45;
    font-weight: 500;
    padding: 10px 16px;
}}
QPushButton#dangerButton {{
    color: #ffced1;
    background: #321a24;
    border-color: #63303e;
}}
QPushButton#dangerButton:hover {{ background: #47202d; }}
QLineEdit, QComboBox, QSpinBox {{
    color: #e5e7ea;
    background: #15191e;
    border: 1px solid {COLORS['border']};
    border-radius: 9px;
    min-height: 24px;
    padding: 8px 12px;
    selection-background-color: {COLORS['primary']};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border-color: #398cff;
}}
QComboBox {{ padding-right: 30px; }}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border: none;
}}
QComboBox QAbstractItemView {{
    color: #e5e7ea;
    background: #20242a;
    border: 1px solid #3a4048;
    selection-background-color: #315f94;
    selection-color: #ffffff;
    padding: 4px;
    outline: none;
}}
QComboBox#transactionTypeCombo {{
    color: #e5e7ea;
    background: #20242a;
    border: 1px solid #3a414a;
    border-radius: 10px;
    padding: 4px 28px 4px 10px;
}}
QCheckBox {{ color: #dfe2e6; spacing: 8px; }}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid #858c95;
    border-radius: 4px;
    background: #15181c;
}}
QCheckBox::indicator:checked {{
    background: {COLORS['primary']};
    border-color: #5ca0ff;
}}
QFrame#contentCard, QFrame#settingsCard, QFrame#transactionsCard,
QFrame#dashboardCard {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 14px;
}}
QTableWidget#genericTable, QTableWidget#rulesTable {{
    color: #dfe2e6;
    background: {COLORS['surface']};
    alternate-background-color: #1a1e23;
    border: none;
    outline: none;
    selection-background-color: #293a50;
    selection-color: #ffffff;
}}
QTableWidget#genericTable::item, QTableWidget#rulesTable::item {{
    border-bottom: 1px solid {COLORS['border_soft']};
    padding: 0 14px;
}}
QHeaderView::section {{
    color: #eef0f3;
    background: #1c2026;
    border: none;
    border-bottom: 1px solid {COLORS['border']};
    padding: 10px 14px;
    font-weight: 650;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 3px 1px;
}}
QScrollBar::handle:vertical {{
    background: #4a5058;
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QMenu {{
    color: #e5e7ea;
    background: #20242a;
    border: 1px solid #3a4048;
    padding: 6px;
}}
QMenu::item {{ padding: 8px 24px 8px 10px; border-radius: 6px; }}
QMenu::item:selected {{ background: #315f94; }}
QDialog {{ background: {COLORS['canvas']}; }}
QMessageBox {{ background: {COLORS['canvas']}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)

