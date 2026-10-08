from __future__ import annotations

from PySide6.QtCore import QDate, QPointF, QRect, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPalette,
    QPen,
    QPolygonF,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QCalendarWidget,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QToolButton,
    QWidget,
)

from app.ui.theme import COLORS, set_button_icon


class DatePickerCalendar(QCalendarWidget):
    """Calendar with custom-painted date cells that match the app theme."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.footer = QFrame(self)
        self.footer.setObjectName("datePickerFooter")
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(14, 12, 14, 12)
        footer_layout.setSpacing(10)

        self.today_button = QPushButton("Today", self.footer)
        self.today_button.setObjectName("datePickerTodayButton")
        self.today_button.setFixedHeight(38)
        self.today_button.clicked.connect(self._select_today)
        footer_layout.addWidget(self.today_button)
        footer_layout.addStretch()

        self.done_button = QPushButton("Done", self.footer)
        self.done_button.setObjectName("datePickerDoneButton")
        self.done_button.setFixedHeight(38)
        self.done_button.clicked.connect(self._close_popup)
        footer_layout.addWidget(self.done_button)

        root_layout = self.layout()
        if root_layout is not None:
            root_layout.addWidget(self.footer)

    def _select_today(self) -> None:
        today = QDate.currentDate()
        if self.minimumDate() <= today <= self.maximumDate():
            self.setSelectedDate(today)
            self.showSelectedDate()

    def _close_popup(self) -> None:
        self.window().hide()

    def paintCell(self, painter: QPainter, rect: QRect, value: QDate) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        selected = value == self.selectedDate()
        in_shown_month = (
            value.month() == self.monthShown()
            and value.year() == self.yearShown()
        )
        enabled = self.minimumDate() <= value <= self.maximumDate()
        cell = rect.adjusted(3, 3, -3, -3)

        if selected:
            background = COLORS["primary"]
            border = "#3691ff"
            foreground = "#ffffff"
        elif in_shown_month:
            background = "#1a2129"
            border = "#252f3a"
            foreground = "#e8edf7" if enabled else "#596372"
        else:
            background = "#161c23"
            border = "#1c242d"
            foreground = "#657080" if enabled else "#4b5563"

        painter.setBrush(QColor(background))
        painter.setPen(QPen(QColor(border), 1.0))
        painter.drawRoundedRect(cell, 8, 8)

        font = painter.font()
        font.setWeight(
            QFont.Weight.DemiBold if selected else QFont.Weight.Normal
        )
        painter.setFont(font)
        painter.setPen(QColor(foreground))
        painter.drawText(cell, Qt.AlignmentFlag.AlignCenter, str(value.day()))
        painter.restore()


class DatePickerEdit(QDateEdit):
    """Application date field with a consistently styled calendar popup."""

    def __init__(
        self,
        value: QDate | None = None,
        parent: QWidget | None = None,
    ) -> None:
        if value is None:
            super().__init__(parent)
        else:
            super().__init__(value, parent)

        self.setObjectName("datePickerEdit")
        self.setCalendarPopup(True)
        self.setDisplayFormat("MMM d, yyyy")
        self.setStyleSheet(self._editor_stylesheet())
        calendar = DatePickerCalendar(self)
        self.setCalendarWidget(calendar)
        self._configure_calendar(calendar)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = COLORS["text_muted"] if self.isEnabled() else COLORS["text_dim"]
        pen = QPen(QColor(color), 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        center = QPointF(self.width() - 20, self.height() / 2)
        painter.drawPolyline(QPolygonF((
            QPointF(center.x() - 4, center.y() - 2),
            QPointF(center.x(), center.y() + 2),
            QPointF(center.x() + 4, center.y() - 2),
        )))

    @staticmethod
    def _configure_calendar(calendar: QCalendarWidget) -> None:
        calendar.setObjectName("financeDatePickerCalendar")
        calendar.setGridVisible(False)
        calendar.setFirstDayOfWeek(Qt.DayOfWeek.Sunday)
        calendar.setHorizontalHeaderFormat(
            QCalendarWidget.HorizontalHeaderFormat.ShortDayNames
        )
        calendar.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )
        calendar.setMinimumSize(420, 404)

        palette = calendar.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#131920"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#131920"))
        palette.setColor(QPalette.ColorRole.Text, QColor(COLORS["text"]))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(COLORS["text"]))
        palette.setColor(QPalette.ColorRole.Button, QColor("#1b222a"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLORS["text"]))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(COLORS["primary"]))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.Text,
            QColor("#596372"),
        )
        calendar.setPalette(palette)

        weekday_format = QTextCharFormat()
        weekday_format.setForeground(QColor("#99a5b7"))
        weekday_format.setFontWeight(600)
        for weekday in Qt.DayOfWeek:
            calendar.setWeekdayTextFormat(weekday, weekday_format)

        for object_name, icon_name in (
            ("qt_calendar_prevmonth", "fa6s.chevron-left"),
            ("qt_calendar_nextmonth", "fa6s.chevron-right"),
        ):
            button = calendar.findChild(QToolButton, object_name)
            if button is not None:
                button.setText("")
                button.setFixedSize(38, 38)
                set_button_icon(
                    button,
                    icon_name,
                    color="#b8c4d8",
                    active_color="#ffffff",
                    size=15,
                )

        calendar.setStyleSheet(DatePickerEdit._calendar_stylesheet())

    @staticmethod
    def _editor_stylesheet() -> str:
        return f"""
            QDateEdit#datePickerEdit {{
                color: {COLORS['text']};
                background: #151b22;
                border: 1px solid #3a4552;
                border-radius: 10px;
                padding: 8px 48px 8px 13px;
                selection-background-color: {COLORS['primary']};
            }}
            QDateEdit#datePickerEdit:hover {{
                border-color: #4b5867;
            }}
            QDateEdit#datePickerEdit:focus {{
                border-color: #398cff;
            }}
            QDateEdit#datePickerEdit:disabled {{
                color: {COLORS['text_dim']};
                background: #12171d;
                border-color: #29313a;
            }}
            QDateEdit#datePickerEdit::drop-down {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 40px;
                border: none;
                border-left: 1px solid #303944;
                border-top-right-radius: 10px;
                border-bottom-right-radius: 10px;
                background: transparent;
            }}
            QDateEdit#datePickerEdit::drop-down:hover {{
                background: #1d252e;
            }}
            QDateEdit#datePickerEdit::down-arrow {{
                image: none;
                width: 0;
                height: 0;
            }}
        """

    @staticmethod
    def _calendar_stylesheet() -> str:
        return f"""
            QCalendarWidget#financeDatePickerCalendar {{
                background: #131920;
                border: 1px solid #394451;
                border-radius: 12px;
            }}
            QCalendarWidget#financeDatePickerCalendar QWidget {{
                color: {COLORS['text']};
                background: #131920;
            }}
            QCalendarWidget QWidget#qt_calendar_navigationbar {{
                background: #151c24;
                border-bottom: 1px solid #29323c;
                min-height: 52px;
                padding: 7px 10px;
            }}
            QCalendarWidget QToolButton {{
                color: {COLORS['text']};
                background: transparent;
                border: 1px solid transparent;
                border-radius: 9px;
                padding: 7px 10px;
                font-size: 14px;
                font-weight: 650;
            }}
            QCalendarWidget QToolButton:hover {{
                background: #202833;
                border-color: #35414e;
            }}
            QCalendarWidget QToolButton#qt_calendar_prevmonth,
            QCalendarWidget QToolButton#qt_calendar_nextmonth {{
                background: #1b222a;
                border-color: #303a45;
                padding: 0;
            }}
            QCalendarWidget QToolButton::menu-indicator {{
                image: none;
            }}
            QCalendarWidget QSpinBox#qt_calendar_yearedit {{
                color: {COLORS['text']};
                background: #1b222a;
                border: 1px solid #35414e;
                border-radius: 8px;
                selection-background-color: {COLORS['primary']};
                padding: 5px 8px;
            }}
            QCalendarWidget QAbstractItemView:enabled {{
                color: #e8edf7;
                background: #131920;
                alternate-background-color: #131920;
                selection-color: #ffffff;
                selection-background-color: {COLORS['primary']};
                border: none;
                outline: none;
                font-size: 12px;
            }}
            QCalendarWidget QFrame#datePickerFooter {{
                background: #131920;
                border: none;
                border-top: 1px solid #29323c;
            }}
            QCalendarWidget QPushButton#datePickerTodayButton,
            QCalendarWidget QPushButton#datePickerDoneButton {{
                min-width: 82px;
                border-radius: 9px;
                padding: 0 18px;
                font-size: 13px;
                font-weight: 650;
            }}
            QCalendarWidget QPushButton#datePickerTodayButton {{
                color: #3d96ff;
                background: transparent;
                border: 1px solid #246eb8;
            }}
            QCalendarWidget QPushButton#datePickerTodayButton:hover {{
                color: #68adff;
                background: #17283a;
                border-color: #398cff;
            }}
            QCalendarWidget QPushButton#datePickerDoneButton {{
                color: #ffffff;
                background: {COLORS['primary']};
                border: 1px solid #3189ff;
            }}
            QCalendarWidget QPushButton#datePickerDoneButton:hover {{
                background: #2589ff;
                border-color: #58a4ff;
            }}
            QCalendarWidget QPushButton#datePickerTodayButton:pressed,
            QCalendarWidget QPushButton#datePickerDoneButton:pressed {{
                padding-top: 1px;
            }}
        """
