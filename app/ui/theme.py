from __future__ import annotations

import re

import qtawesome as qta
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication, QAbstractButton, QLabel, QMenu

from app.core.paths import ICONS_DIR, PROJECT_ROOT
from app.ui.widgets.input_behavior import apply_interactive_cursor


APP_ROOT = PROJECT_ROOT
ICON_ROOT = ICONS_DIR

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

ICON_TEXT_SPACING = 8
_NATIVE_BUTTON_ICON_TEXT_SPACING = 4


_qtawesome_available: bool | None = None


def icon_render_device_pixel_ratio() -> float:
    """Render icons at native display density, with 2x supersampling minimum."""
    app = QApplication.instance()
    screen_ratios = (
        [screen.devicePixelRatio() for screen in app.screens()]
        if app is not None
        else []
    )
    return max(2.0, *screen_ratios)


def high_dpi_canvas(width: int, height: int | None = None) -> QPixmap:
    """Create a transparent pixmap whose logical dimensions stay unchanged."""
    logical_height = width if height is None else height
    ratio = icon_render_device_pixel_ratio()
    pixmap = QPixmap(
        max(1, round(width * ratio)),
        max(1, round(logical_height * ratio)),
    )
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    return pixmap


def icon_pixmap(
    icon: QIcon,
    width: int,
    height: int | None = None,
    mode: QIcon.Mode = QIcon.Mode.Normal,
    state: QIcon.State = QIcon.State.Off,
) -> QPixmap:
    """Rasterize a scalable icon sharply without changing its logical size."""
    logical_height = width if height is None else height
    ratio = icon_render_device_pixel_ratio()
    size = QSize(width, logical_height)
    try:
        return icon.pixmap(size, ratio, mode, state)
    except TypeError:
        # Compatibility fallback for older Qt bindings without the DPR overload.
        pixmap = icon.pixmap(
            QSize(round(width * ratio), round(logical_height * ratio)),
            mode,
            state,
        )
        pixmap.setDevicePixelRatio(ratio)
        return pixmap


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
    apply_interactive_cursor(button)
    button._finance_base_icon = awesome_icon(  # type: ignore[attr-defined]
        name, color=color, active_color=active_color
    )
    button._finance_icon_size = size  # type: ignore[attr-defined]
    refresh_button_icon_spacing(button)


def _icon_with_right_padding(icon: QIcon, size: int, padding: int) -> QIcon:
    """Preserve icon modes while extending its canvas on the text-facing side."""
    if icon.isNull() or padding <= 0:
        return icon
    padded = QIcon()
    for mode in (
        QIcon.Mode.Normal,
        QIcon.Mode.Disabled,
        QIcon.Mode.Active,
        QIcon.Mode.Selected,
    ):
        for state in (QIcon.State.Off, QIcon.State.On):
            canvas = high_dpi_canvas(size + padding, size)
            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(0, 0, icon_pixmap(icon, size, size, mode, state))
            painter.end()
            padded.addPixmap(canvas, mode, state)
    return padded


def spaced_text_icon(icon: QIcon, size: int = 16) -> QIcon:
    """Return an icon canvas that yields the standard 8 px icon/text gap."""
    return _icon_with_right_padding(
        icon,
        size,
        max(0, ICON_TEXT_SPACING - _NATIVE_BUTTON_ICON_TEXT_SPACING),
    )


def spaced_text_icon_size(size: int = 16) -> QSize:
    return QSize(
        size + max(0, ICON_TEXT_SPACING - _NATIVE_BUTTON_ICON_TEXT_SPACING),
        size,
    )


def refresh_button_icon_spacing(button: QAbstractButton) -> None:
    """Keep an 8 px visual gap for text buttons and centered icon-only controls."""
    icon = getattr(button, "_finance_base_icon", button.icon())
    size = int(getattr(button, "_finance_icon_size", button.iconSize().height()))
    has_text = bool(button.text().strip())
    extra_padding = (
        max(0, ICON_TEXT_SPACING - _NATIVE_BUTTON_ICON_TEXT_SPACING)
        if has_text
        else 0
    )
    button.setIcon(_icon_with_right_padding(icon, size, extra_padding))
    button.setIconSize(QSize(size + extra_padding, size))
    button.setProperty("iconTextSpacing", ICON_TEXT_SPACING if has_text else 0)


def set_icon_only_button(
    button: QAbstractButton,
    name: str,
    *,
    tooltip: str | None = None,
    color: str = COLORS["text_muted"],
    active_color: str = COLORS["text"],
    icon_size: int = 16,
    button_size: int = 38,
) -> None:
    """Configure a compact accessible icon-only button."""
    label = button.text().strip()
    description = tooltip or button.toolTip() or label
    if description:
        button.setToolTip(description)
        if not button.accessibleName():
            button.setAccessibleName(description)
    button.setText("")
    button.setProperty("iconOnly", True)
    button.setFixedSize(button_size, button_size)
    set_button_icon(
        button,
        name,
        color=color,
        active_color=active_color,
        size=icon_size,
    )


def set_delete_button_icon(button: QAbstractButton, *, size: int = 15) -> None:
    """Turn a destructive button into a consistent trash-can control."""
    set_icon_only_button(
        button,
        "fa6s.trash",
        color="#ff9da0",
        active_color=COLORS["negative"],
        icon_size=size,
        button_size=max(38, size + 22),
    )


def prepare_popup_menu(menu: QMenu) -> QMenu:
    """Apply the shared flush popup treatment without a native drop shadow."""
    menu.setWindowFlags(
        menu.windowFlags() | Qt.WindowType.NoDropShadowWindowHint
    )
    menu.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
    return menu


def set_label_icon(
    label: QLabel,
    name: str,
    *,
    color: str = COLORS["text_muted"],
    size: int = 18,
) -> None:
    label.setPixmap(icon_pixmap(awesome_icon(name, color=color), size, size))
    label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)


def brand_icon(institution: str, *, size: int = 24) -> QIcon:
    """Return known institution artwork, with a neutral bank fallback."""
    normalized = " ".join(re.findall(r"[a-z0-9]+", institution.casefold()))
    words = set(normalized.split())
    if "american express" in normalized or "amex" in words:
        path = ICON_ROOT / "amex_icon.png"
        crop_td = False
    elif normalized == "td" or "toronto dominion" in normalized:
        path = ICON_ROOT / "td_icon.jpg"
        crop_td = True
    elif "rbc" in words or "royal bank of canada" in normalized:
        path = ICON_ROOT / "rbc.png"
        crop_td = False
    elif "wealthsimple" in words:
        path = ICON_ROOT / "wealthsimple.png"
        crop_td = False
    elif "canada life" in normalized:
        path = ICON_ROOT / "canada-life.png"
        crop_td = False
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

    target = high_dpi_canvas(size, size)
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
        (("food", "restaurant", "dining"), "fa6s.utensils"),
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
QWidget#investmentsPage, QWidget#investmentsContent,
QWidget#categoriesPage, QWidget#settingsPage, QWidget#welcomePage,
QWidget#addUserPage, QWidget#userManagementPage,
QWidget#userManagementContent {{
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
    font-size: 24px;
    font-weight: 750;
}}
QLabel#dialogSubtitle {{
    color: #aebbd0;
    font-size: 14px;
}}
QDialog#genericDialog {{ background: transparent; }}
QFrame#dialogCard {{
    background: #111820;
    border: 1px solid #344351;
    border-radius: 16px;
}}
QWidget#dialogHeader, QWidget#dialogContent, QWidget#dialogFooter {{
    background: transparent;
    border: none;
}}
QFrame#dialogIconFrame {{
    background: #14243a;
    border: 1px solid #23496f;
    border-radius: 14px;
}}
QToolButton#dialogCloseButton {{
    background: transparent;
    border: none;
    border-radius: 8px;
}}
QToolButton#dialogCloseButton:hover {{ background: #25303b; }}
QFrame#dialogInfoPanel {{
    background: #132238;
    border: 1px solid #284d72;
    border-radius: 11px;
}}
QLabel#dialogInfoText {{ color: #afc6e8; font-size: 12px; }}
QFrame#dialogFooterDivider {{
    color: #2d3945;
    border: none;
    border-top: 1px solid #2d3945;
    max-height: 1px;
}}
QPushButton#dialogCancelButton {{
    color: #e0e6ed;
    background: #18212b;
    border: 1px solid #3a4857;
    font-weight: 600;
}}
QPushButton#dialogCancelButton:hover {{
    color: #ffffff;
    background: #222e3a;
    border-color: #536476;
}}
QDialog#genericDialog QLineEdit,
QDialog#genericDialog QComboBox,
QDialog#genericDialog QSpinBox,
QDialog#genericDialog QDoubleSpinBox,
QDialog#genericDialog QDateEdit {{
    min-height: 30px;
    padding: 9px 12px;
    background: #111923;
    border-color: #344657;
}}
QLabel#dialogFieldLabel {{
    color: #e1e8f2;
    font-size: 13px;
    font-weight: 650;
}}
QFrame#dialogDisplayField {{
    background: #111923;
    border: 1px solid #344657;
    border-radius: 10px;
}}
QLabel#dialogDisplayValue {{ color: #edf2f7; font-size: 14px; }}
QLabel#investmentDialogSectionTitle {{
    color: {COLORS['text']};
    font-size: 14px;
    font-weight: 700;
}}
QLabel#investmentDialogSectionSubtitle {{
    color: {COLORS['text_muted']};
    font-size: 11px;
}}
QLabel#workRrspInfoNote {{
    color: #9db8e8;
    background: #14213a;
    border: 1px solid #294d87;
    border-radius: 8px;
    font-size: 11px;
}}
QLabel#sectionTitle {{
    color: {COLORS['text']};
    font-size: 15px;
    font-weight: 650;
}}
QLabel#settingsOptionTitle {{
    color: {COLORS['text']};
    font-size: 14px;
    font-weight: 600;
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
    color: #69b4ff;
    background: #141c25;
    border-color: #285f98;
    font-weight: 550;
    padding: 9px 15px;
}}
QPushButton#secondaryActionButton:hover {{
    color: #ffffff;
    background: #173152;
    border-color: #3c8ee1;
}}
QPushButton#secondaryActionButton:pressed {{ background: #122844; }}
QPushButton#dangerButton {{
    color: #ffced1;
    background: #321a24;
    border-color: #63303e;
}}
QPushButton#dangerButton:hover {{ background: #47202d; }}
QLabel#duplicateCount {{
    color: {COLORS['text']};
    font-size: 14px;
    font-weight: 650;
}}
QScrollArea#duplicateReviewScroll,
QScrollArea#duplicateReviewScroll > QWidget > QWidget {{
    background: transparent;
    border: none;
}}
QFrame#duplicateReviewCard {{
    background: #151c24;
    border: 1px solid #303b47;
    border-radius: 12px;
}}
QFrame#duplicateReviewCard[decision="keep"] {{ border-color: #277a5b; }}
QFrame#duplicateReviewCard[decision="skip"] {{ border-color: #68404a; }}
QFrame#duplicateDetailsPanel {{
    background: #111820;
    border: 1px solid #293541;
    border-radius: 9px;
}}
QLabel#duplicateDetailsTitle {{
    color: {COLORS['text_muted']};
    font-size: 11px;
    font-weight: 700;
}}
QLabel#duplicateDetailsText {{ color: #e7ebf0; }}
QLabel#duplicateAmount {{ color: #ffffff; font-size: 15px; font-weight: 700; }}
QLabel#duplicateReason {{ color: #9db8d6; }}
QPushButton#duplicateKeepButton {{
    color: #a9f2d2;
    background: #152820;
    border-color: #295d48;
}}
QPushButton#duplicateKeepButton:hover,
QPushButton#duplicateKeepButton[selected="true"] {{
    color: #ffffff;
    background: #1b6448;
    border-color: #2fa775;
}}
QPushButton#duplicateSkipButton {{
    color: #f0b5bb;
    background: #281a20;
    border-color: #56313d;
}}
QPushButton#duplicateSkipButton:hover,
QPushButton#duplicateSkipButton[selected="true"] {{
    color: #ffffff;
    background: #693041;
    border-color: #a64a61;
}}
QPushButton[iconOnly="true"] {{
    min-width: 38px;
    max-width: 38px;
    min-height: 38px;
    max-height: 38px;
    padding: 0;
}}
QPushButton#dangerButton[iconOnly="true"] {{
    background: transparent;
    border-color: transparent;
}}
QPushButton#dangerButton[iconOnly="true"]:hover {{
    background: #47202d;
    border-color: #713543;
}}
QPushButton#tableIconButton {{
    background: transparent;
    border-color: transparent;
}}
QPushButton#tableIconButton:hover {{
    background: {COLORS['surface_hover']};
    border-color: {COLORS['border']};
}}
QPushButton#transactionActionButton,
QToolButton#goalsMenuButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 0;
}}
QPushButton#transactionActionButton:hover,
QToolButton#goalsMenuButton:hover {{
    background: {COLORS['surface_hover']};
    border-color: {COLORS['border']};
}}
QPushButton#transactionActionButton:pressed,
QToolButton#goalsMenuButton:pressed {{
    background: #15181d;
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit {{
    color: #e5e7ea;
    background: #15191e;
    border: 1px solid {COLORS['border']};
    border-radius: 9px;
    min-height: 24px;
    padding: 8px 12px;
    selection-background-color: {COLORS['primary']};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateEdit:focus {{
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
    padding: 0;
    margin: 0;
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    color: #e5e7ea;
    background: transparent;
    border: none;
    min-height: 24px;
    padding: 7px 10px;
}}
QComboBox QAbstractItemView::item:hover {{ background: #2a3038; }}
QComboBox QAbstractItemView::item:selected {{
    color: #ffffff;
    background: #315f94;
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
QFrame#investmentSummaryCard {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 14px;
}}
QFrame#recentInvestmentEntry {{
    background: {COLORS['surface_alt']};
    border: 1px solid {COLORS['border_soft']};
    border-radius: 9px;
}}
QFrame#investmentDialogSection {{
    background: #11161c;
    border: 1px solid {COLORS['border']};
    border-radius: 11px;
}}
QFrame#workRrspToggleCard {{
    background: #131920;
    border: 1px solid {COLORS['border']};
    border-radius: 9px;
}}
QFrame#workRrspToggleCard[selected="true"] {{
    background: #14203a;
    border-color: #397df1;
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
    padding: 4px 6px;
    margin: 0;
}}
QMenu::item {{
    background: transparent;
    padding: 8px 24px 8px 12px;
    margin: 0;
}}
QMenu::item:selected {{ background: #315f94; }}
QDialog {{ background: {COLORS['canvas']}; }}
QMessageBox {{ background: {COLORS['canvas']}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)

