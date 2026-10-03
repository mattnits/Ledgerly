import logging
from datetime import date

from PySide6.QtCore import (
    QObject,
    QRunnable,
    QSignalBlocker,
    QThreadPool,
    QTimer,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QComboBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from database.db import SessionLocal
from database.category_rules import rule_prefill_from_transaction
from database.models import Category, Transaction
from database.transactions import (
    TransactionQueryParams,
    TransactionQueryResult,
    fetch_transactions,
    get_visible_transaction,
    set_transaction_deleted,
)
from ui.components.generic_table import GenericTable
from ui.components.loading_state import LoadingOverlay
from ui.components.period_selector import PeriodSelector
from ui.components.transaction_row import TransactionRow
from ui.theme import (
    awesome_icon,
    brand_icon,
    category_icon_name,
    transaction_type_icon,
)
from utils.constants import (
    CATEGORY_FREE_TRANSACTION_TYPES,
    ClassificationSource,
    TRANSACTION_TYPE_LABELS,
    TransactionType,
)


logger = logging.getLogger(__name__)


class _QuerySignals(QObject):
    succeeded = Signal(int, int, int, object)
    failed = Signal(int, int, int, object)


class _TransactionQueryWorker(QRunnable):
    def __init__(
        self,
        generation: int,
        request_id: int,
        params: TransactionQueryParams,
        query_loader,
        session_factory,
    ):
        super().__init__()
        self.generation = generation
        self.request_id = request_id
        self.params = params
        self.query_loader = query_loader
        self.session_factory = session_factory
        self.signals = _QuerySignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.query_loader(
                self.params,
                session_factory=self.session_factory,
            )
        except Exception as exc:
            logger.exception(
                "Transaction query failed (generation=%s, offset=%s)",
                self.generation,
                self.params.offset,
            )
            self.signals.failed.emit(
                self.generation,
                self.request_id,
                self.params.offset,
                exc,
            )
            return
        self.signals.succeeded.emit(
            self.generation,
            self.request_id,
            self.params.offset,
            result,
        )


class StatementsTable(QWidget):
    create_rule_requested = Signal(object)
    count_changed = Signal(int)
    loading_changed = Signal(bool)

    PAGE_SIZE = 200
    COLUMN_HEADERS = (
        "Date", "Description", "Amount", "Account", "Transaction Type",
        "Category", "Imported At", "Action",
    )
    DESCRIPTION_COLUMN = 1
    MINIMUM_COLUMN_WIDTHS = {
        0: 100,
        1: 220,
        2: 90,
        3: 130,
        4: 190,
        5: 145,
        6: 120,
        7: 56,
    }
    MAXIMUM_COLUMN_WIDTHS = {
        0: 124,
        1: 320,
        2: 112,
        3: 190,
        4: 232,
        5: 200,
        6: 160,
        7: 76,
    }

    def __init__(
        self,
        parent=None,
        session_factory=SessionLocal,
        query_loader=fetch_transactions,
        thread_pool: QThreadPool | None = None,
    ):
        super().__init__(parent)
        self.session_factory = session_factory
        self.query_loader = query_loader
        self._thread_pool = thread_pool or QThreadPool.globalInstance()
        self._query_generation = 0
        self._request_serial = 0
        self._active_workers: dict[int, _TransactionQueryWorker] = {}
        self._request_contexts: dict[int, dict] = {}
        self._last_failed_context: dict | None = None
        self.user_id: str | None = None
        self.group_id: int | None = None
        self.rows: list[TransactionRow] = []
        self.category_options: list[tuple[int, str, str]] = []
        self.total_count = 0
        self.filtered_count = 0
        self.loaded_count = 0
        self._loading = False
        self.sort_column = 0
        self.sort_order = Qt.SortOrder.DescendingOrder
        self.category_filter: int | str | None = "all"
        self.transaction_type_filter: TransactionType | str = "all"
        self.account_filter: int | str = "all"
        self.needs_review_filter = False
        self.period_filter = "monthly"
        self.date_range_filter = "this_month"
        today = date.today()
        self.selected_month = (today.year, today.month)
        self.available_months: set[tuple[int, int]] = set()
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._reset_and_apply)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(16)

        toolbar = QWidget()
        toolbar.setObjectName("transactionsToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(14)

        self.period_selector = PeriodSelector()
        self.period_selector.selection_changed.connect(self._select_period)
        toolbar_layout.addWidget(self.period_selector)
        self.monthly_button = self.period_selector.monthly_button
        self.all_time_button = self.period_selector.all_time_button
        self.month_selector = self.period_selector.month_selector

        self.count_label = QLabel("0 transactions")
        self.count_label.setObjectName("transactionsCount")
        self.review_mode_label = QLabel("Needs Review mode")
        self.review_mode_label.setObjectName("reviewModeLabel")
        self.review_mode_label.hide()
        toolbar_layout.addWidget(self.review_mode_label)
        toolbar_layout.addStretch()

        self.search = QLineEdit()
        self.search.setObjectName("transactionSearch")
        self.search.setPlaceholderText("Search transactions...")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(350)
        self.search.addAction(
            awesome_icon("fa6s.magnifying-glass", color="#a7adb5"),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.search.textChanged.connect(self._schedule_search)
        toolbar_layout.addWidget(self.search)

        outer_layout.addWidget(toolbar)

        filter_bar = QFrame()
        filter_bar.setObjectName("filterBar")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(16, 13, 16, 13)
        filter_layout.setSpacing(14)

        self.account_selector = QComboBox()
        self.account_selector.addItem(
            awesome_icon("fa6s.wallet", color="#b2b8c1"),
            "All Accounts",
            "all",
        )
        self.account_selector.currentIndexChanged.connect(self._select_account)
        self._add_filter_field(filter_layout, "Account", self.account_selector)

        self.category_selector = QComboBox()
        self.category_selector.addItem(
            awesome_icon("fa6s.tags", color="#ffffff"),
            "All Categories",
            "all",
        )
        self.category_selector.setItemData(
            0,
            QColor("#ffffff"),
            Qt.ItemDataRole.ForegroundRole,
        )
        self._fit_category_popup()
        self.category_selector.currentIndexChanged.connect(self._select_category)
        self._add_filter_field(filter_layout, "Category", self.category_selector)

        self.transaction_type_selector = QComboBox()
        self.transaction_type_selector.setFixedWidth(230)
        self.transaction_type_selector.addItem(
            awesome_icon("fa6s.credit-card", color="#b2b8c1"),
            "All Transaction Types",
            "all",
        )
        for transaction_type, label in TRANSACTION_TYPE_LABELS.items():
            self.transaction_type_selector.addItem(
                transaction_type_icon(transaction_type), label, transaction_type
            )
        transaction_filter_width = max(
            230,
            self.transaction_type_selector.sizeHint().width() + 8,
            max(
                self.transaction_type_selector.fontMetrics().horizontalAdvance(label)
                for label in (
                    "All Transaction Types",
                    *TRANSACTION_TYPE_LABELS.values(),
                )
            ) + 64,
        )
        self.transaction_type_selector.setFixedWidth(transaction_filter_width)
        self.transaction_type_selector.currentIndexChanged.connect(
            self._select_transaction_type
        )
        self._add_filter_field(
            filter_layout, "Transaction Type", self.transaction_type_selector
        )

        self.needs_review_checkbox = QCheckBox("Needs Review only")
        self.needs_review_checkbox.setObjectName("needsReviewFilter")
        self.needs_review_checkbox.toggled.connect(self._select_needs_review)
        review_field = QWidget()
        review_field_layout = QVBoxLayout(review_field)
        review_field_layout.setContentsMargins(0, 0, 0, 0)
        review_field_layout.setSpacing(3)
        review_spacer = QLabel(" ")
        review_spacer.setObjectName("filterLabel")
        review_field_layout.addWidget(review_spacer)
        review_field_layout.addWidget(self.needs_review_checkbox)
        filter_layout.addWidget(review_field)

        self.date_range_selector = QComboBox()
        for label, value in (
            ("This Month", "this_month"),
            ("Last Month", "last_month"),
            ("Selected Month", "selected_month"),
            ("This Year", "this_year"),
            ("All Time", "all"),
        ):
            self.date_range_selector.addItem(label, value)
        self.date_range_selector.currentIndexChanged.connect(self._select_date_range)
        self._add_filter_field(filter_layout, "Date Range", self.date_range_selector)

        divider = QFrame()
        divider.setObjectName("filterDivider")
        divider.setFrameShape(QFrame.Shape.VLine)
        filter_layout.addWidget(divider)
        self.clear_filters_button = QPushButton("Clear Filters")
        self.clear_filters_button.setObjectName("clearFiltersButton")
        self.clear_filters_button.clicked.connect(self._clear_filters)
        filter_layout.addWidget(self.clear_filters_button)
        outer_layout.addWidget(filter_bar)

        card = QFrame()
        card.setObjectName("transactionsCard")
        outer_layout.addWidget(card, 1)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        self.table = GenericTable(self.COLUMN_HEADERS)
        table_header = self.table.horizontalHeader()
        table_header.setSectionsClickable(True)
        table_header.setMinimumSectionSize(48)
        table_header.sectionClicked.connect(self._sort_by_column)
        table_header.setSortIndicatorShown(False)
        self.table.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.table.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        for column, width in self.MAXIMUM_COLUMN_WIDTHS.items():
            table_header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.Interactive
            )
            self.table.setColumnWidth(column, width)
        self.table.horizontalHeaderItem(2).setTextAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self.table.horizontalHeaderItem(4).setTextAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self._update_sort_headers()
        card_layout.addWidget(self.table, 1)
        QTimer.singleShot(0, self._fit_table_columns)

        self.message = QLabel("No transactions yet")
        self.message.setObjectName("transactionsMessage")
        self.message.hide()
        card_layout.addWidget(self.message)

        footer = QWidget()
        footer.setObjectName("transactionsFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 13, 24, 13)
        footer_layout.setSpacing(6)
        self.range_label = QLabel("Showing 0 transactions")
        self.range_label.setObjectName("transactionsRange")
        footer_layout.addWidget(self.range_label)
        footer_layout.addStretch()

        card_layout.addWidget(footer)

        self.loading_overlay = LoadingOverlay(card)
        self.loading_overlay.retry_requested.connect(self._retry_failed_query)

        self.setStyleSheet("""
            QFrame#transactionsCard {
                background: #171b20;
                border: 1px solid #303740;
                border-radius: 14px;
            }
            QWidget#transactionsFooter {
                background: #171b20;
                border-bottom-left-radius: 14px;
                border-bottom-right-radius: 14px;
            }
            QLabel#transactionsCount, QLabel#transactionsRange,
            QLabel#transactionsMessage {
                color: #a7afb9;
                font-size: 13px;
            }
            QLabel#transactionsCount { padding-left: 10px; }
            QLabel#reviewModeLabel {
                color: #ffd68a;
                background: #392b17;
                border: 1px solid #705327;
                border-radius: 8px;
                padding: 4px 9px;
            }
            QLabel#transactionsMessage { padding: 10px 24px; }
            QLineEdit#transactionSearch {
                color: #e3e5e8;
                background: #191d22;
                border: 1px solid #343b44;
                border-radius: 10px;
                padding: 10px 13px;
                font-size: 14px;
            }
            QLineEdit#transactionSearch:focus { border-color: #398cff; }
            QFrame#filterBar {
                background: #171b20;
                border: 1px solid #303740;
                border-radius: 12px;
            }
            QLabel#filterLabel {
                color: #b4bac2;
                font-size: 12px;
            }
            QComboBox#filterCombo {
                color: #e3e5e8;
                background: #15191e;
                border: 1px solid #343a43;
                border-radius: 8px;
                padding: 8px 30px 8px 12px;
                min-height: 22px;
            }
            QComboBox#filterCombo::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border: none;
                background: transparent;
            }
            QComboBox#filterCombo QAbstractItemView {
                color: #e3e5e8;
                background: #22262b;
                border: 1px solid #40464e;
                selection-background-color: #3b4858;
            }
            QFrame#filterDivider { color: #343a43; }
            QCheckBox#needsReviewFilter {
                color: #ffffff;
                spacing: 7px;
                padding: 8px;
            }
            QPushButton#clearFiltersButton {
                color: #3d9cff;
                background: transparent;
                border: none;
                padding: 8px 10px;
            }
            QPushButton#clearFiltersButton:hover { color: #8bc4ff; }
        """)
        self.needs_review_checkbox.setFixedHeight(
            self.date_range_selector.sizeHint().height()
        )
        self._show_empty_table()

    @staticmethod
    def _add_filter_field(layout: QHBoxLayout, label: str, selector: QComboBox) -> None:
        field = QWidget()
        field_layout = QVBoxLayout(field)
        field_layout.setContentsMargins(0, 0, 0, 0)
        field_layout.setSpacing(3)
        title = QLabel(label)
        title.setObjectName("filterLabel")
        selector.setObjectName("filterCombo")
        selector.setMinimumWidth(max(130, selector.minimumWidth()))
        field_layout.addWidget(title)
        field_layout.addWidget(selector)
        layout.addWidget(field, 1)

    def _fit_category_popup(self) -> None:
        longest_label = max(
            (
                self.category_selector.fontMetrics().horizontalAdvance(
                    self.category_selector.itemText(index)
                )
                for index in range(self.category_selector.count())
            ),
            default=0,
        )
        self.category_selector.view().setMinimumWidth(
            max(220, longest_label + 64)
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "table"):
            QTimer.singleShot(0, self._fit_table_columns)

    def _fit_table_columns(self) -> None:
        """Scale all columns while keeping every field within readable bounds."""
        if self.table.viewport().width() <= 0:
            return

        available = self.table.viewport().width() - 2
        minimum_total = sum(self.MINIMUM_COLUMN_WIDTHS.values())
        maximum_total = sum(self.MAXIMUM_COLUMN_WIDTHS.values())
        scale = min(
            1.0,
            max(
                0.0,
                (available - minimum_total) / (maximum_total - minimum_total),
            ),
        )
        for column, minimum in self.MINIMUM_COLUMN_WIDTHS.items():
            maximum = self.MAXIMUM_COLUMN_WIDTHS[column]
            width = round(minimum + (maximum - minimum) * scale)
            self.table.setColumnWidth(column, width)

    def _month_range_key(self) -> str:
        today = date.today()
        current = (today.year, today.month)
        previous = (today.year - (today.month == 1), (today.month - 2) % 12 + 1)
        if self.selected_month == current:
            return "this_month"
        if self.selected_month == previous:
            return "last_month"
        return "selected_month"

    def _set_date_range_choice(self) -> None:
        with QSignalBlocker(self.date_range_selector):
            index = self.date_range_selector.findData(self.date_range_filter)
            self.date_range_selector.setCurrentIndex(index)

    def _refresh_month_choices(self) -> None:
        self.period_selector.set_available_months(self.available_months)
        self.selected_month = self.period_selector.selected_month
        self.period_filter = self.period_selector.period
        if self.period_filter == "monthly":
            self.date_range_filter = self._month_range_key()
        else:
            self.date_range_filter = "all"
        self._set_date_range_choice()

    def _set_period_filter(self, period: str) -> None:
        self.period_selector.set_period(period)

    def _select_month(self, index: int) -> None:
        month = self.month_selector.itemData(index)
        if month is not None:
            self.period_selector.set_selected_month(month)

    def _select_period(self, period: str, month: tuple[int, int]) -> None:
        self.period_filter = period
        self.selected_month = month
        self.date_range_filter = self._month_range_key() if period == "monthly" else "all"
        self._set_date_range_choice()
        self._apply_filters()

    def _select_account(self, index: int) -> None:
        value = self.account_selector.itemData(index)
        if value is not None:
            self.account_filter = value
            self._apply_filters()

    def _select_category(self, index: int) -> None:
        value = self.category_selector.itemData(index)
        if index >= 0:
            self.category_filter = value
            self._apply_filters()

    def _select_transaction_type(self, index: int) -> None:
        value = self.transaction_type_selector.itemData(index)
        if value is not None:
            self.transaction_type_filter = value
            self._apply_filters()

    def _select_needs_review(self, checked: bool) -> None:
        self.needs_review_filter = checked
        self._apply_filters()

    def _select_date_range(self, index: int) -> None:
        value = self.date_range_selector.itemData(index)
        if value is None:
            return
        self.date_range_filter = value
        today = date.today()
        if value == "this_month":
            self.selected_month = (today.year, today.month)
        elif value == "last_month":
            self.selected_month = (
                today.year - (today.month == 1),
                (today.month - 2) % 12 + 1,
            )
        self.period_filter = "all" if value in ("this_year", "all") else "monthly"
        self.period_selector.set_selected_month(self.selected_month, emit=False)
        self.period_selector.set_period(self.period_filter, emit=False)
        self._apply_filters()

    def _clear_filters(self) -> None:
        today = date.today()
        self.selected_month = (today.year, today.month)
        self.period_filter = "monthly"
        self.date_range_filter = "this_month"
        self.account_filter = "all"
        self.category_filter = "all"
        self.transaction_type_filter = "all"
        self.needs_review_filter = False
        self.period_selector.reset(emit=False)
        with (
            QSignalBlocker(self.account_selector),
            QSignalBlocker(self.category_selector),
            QSignalBlocker(self.transaction_type_selector),
            QSignalBlocker(self.needs_review_checkbox),
            QSignalBlocker(self.search),
        ):
            self.account_selector.setCurrentIndex(0)
            self.category_selector.setCurrentIndex(0)
            self.transaction_type_selector.setCurrentIndex(0)
            self.needs_review_checkbox.setChecked(False)
            self.search.clear()
        self._set_date_range_choice()
        self._apply_filters()

    def set_user_id(self, user_id: str | None) -> None:
        self.set_profile(user_id=user_id)

    def set_profile(
        self,
        *,
        user_id: str | None = None,
        group_id: int | None = None,
    ) -> None:
        self.user_id = user_id
        self.group_id = group_id
        today = date.today()
        self.selected_month = (today.year, today.month)
        self.period_filter = "monthly"
        self.date_range_filter = "this_month"
        self.account_filter = "all"
        self.category_filter = "all"
        self.transaction_type_filter = "all"
        self.needs_review_filter = False
        self.period_selector.reset(emit=False)
        self._set_date_range_choice()
        with QSignalBlocker(self.search), QSignalBlocker(self.needs_review_checkbox):
            self.search.clear()
            self.needs_review_checkbox.setChecked(False)
        self.reload()

    def reload(self) -> None:
        self._apply_filters()

    def _update_filter_options(
        self,
        accounts: tuple[tuple[int, str, str], ...],
        categories: tuple[tuple[int, str, str], ...],
        available_months: frozenset[tuple[int, int]],
    ) -> None:
        self.category_options = list(categories)
        self.available_months = set(available_months)
        self._refresh_month_choices()
        with QSignalBlocker(self.account_selector):
            self.account_selector.clear()
            self.account_selector.addItem(
                    awesome_icon("fa6s.wallet", color="#b2b8c1"),
                "All Accounts",
                "all",
            )
            for account_id, name, institution in accounts:
                self.account_selector.addItem(
                    brand_icon(institution), f"{name} ({institution})", account_id
                )
            selected = self.account_selector.findData(self.account_filter)
            if selected < 0:
                self.account_filter = "all"
                selected = 0
            self.account_selector.setCurrentIndex(selected)
        with QSignalBlocker(self.category_selector):
            self.category_selector.clear()
            self.category_selector.addItem(
                awesome_icon("fa6s.tags", color="#ffffff"),
                "All Categories",
                "all",
            )
            self.category_selector.addItem(
                awesome_icon("fa6s.trash", color="#ffffff"),
                "Removed Transactions",
                "deleted",
            )
            self.category_selector.addItem(
                awesome_icon("fa6s.tag", color="#ffffff"),
                "Uncategorized",
                None,
            )
            for category_id, name, _color in self.category_options:
                self.category_selector.addItem(
                    awesome_icon(category_icon_name(name), color="#ffffff"),
                    name,
                    category_id,
                )
            for index in range(self.category_selector.count()):
                self.category_selector.setItemData(
                    index,
                    QColor("#ffffff"),
                    Qt.ItemDataRole.ForegroundRole,
                )
            self._fit_category_popup()
            selected = self.category_selector.findData(self.category_filter)
            if selected < 0:
                self.category_filter = "all"
                selected = 0
            self.category_selector.setCurrentIndex(selected)
        with QSignalBlocker(self.transaction_type_selector):
            selected = self.transaction_type_selector.findData(
                self.transaction_type_filter
            )
            if selected < 0:
                self.transaction_type_filter = "all"
                selected = 0
            self.transaction_type_selector.setCurrentIndex(selected)

    def _schedule_search(self) -> None:
        self._query_generation += 1
        self._set_loading(True)
        self.loading_overlay.show_loading("Loading transactions...")
        self._search_timer.start()

    def _set_loading(self, loading: bool) -> None:
        loading = bool(loading)
        if loading == self._loading:
            return
        self._loading = loading
        self.loading_changed.emit(loading)

    def _reset_and_apply(self) -> None:
        self._apply_filters()

    def _sort_by_column(self, column: int) -> None:
        if column == len(self.COLUMN_HEADERS) - 1:
            return
        if column == self.sort_column:
            self.sort_order = (
                Qt.SortOrder.AscendingOrder
                if self.sort_order == Qt.SortOrder.DescendingOrder
                else Qt.SortOrder.DescendingOrder
            )
        else:
            self.sort_column = column
            self.sort_order = (
                Qt.SortOrder.DescendingOrder if column in (0, 2, 6)
                else Qt.SortOrder.AscendingOrder
            )
        self._update_sort_headers()
        self._apply_filters()

    def _update_sort_headers(self) -> None:
        arrow = "↑" if self.sort_order == Qt.SortOrder.AscendingOrder else "↓"
        for index, label in enumerate(self.COLUMN_HEADERS):
            self.table.horizontalHeaderItem(index).setText(
                f"{label} {arrow}" if index == self.sort_column else label
            )

    def _on_scroll(self, value: int) -> None:
        scrollbar = self.table.verticalScrollBar()
        if scrollbar.maximum() > 0 and value >= (
            scrollbar.maximum() - self.table.verticalHeader().defaultSectionSize() * 2
        ):
            self._load_more()

    def _apply_filters(self, preserve_scroll: bool = False) -> None:
        self._search_timer.stop()
        vertical_scrollbar = self.table.verticalScrollBar()
        horizontal_scrollbar = self.table.horizontalScrollBar()
        scroll_position = vertical_scrollbar.value() if preserve_scroll else 0
        horizontal_position = horizontal_scrollbar.value() if preserve_scroll else 0
        previously_loaded = self.loaded_count if preserve_scroll else 0
        self.review_mode_label.setVisible(self.needs_review_filter)
        self._query_generation += 1
        if self.user_id is None and self.group_id is None:
            self._set_loading(False)
            self.loading_overlay.hide_loading()
            self._update_filter_options((), (), frozenset())
            self._show_empty_table()
            return

        limit = max(self.PAGE_SIZE, previously_loaded) if preserve_scroll else self.PAGE_SIZE
        context = {
            "kind": "replace",
            "preserve_scroll": preserve_scroll,
            "scroll_position": scroll_position,
            "horizontal_position": horizontal_position,
            "limit": limit,
        }
        self._start_query(offset=0, limit=limit, context=context)

    def _load_more(self) -> None:
        if (
            self._loading
            or (self.user_id is None and self.group_id is None)
            or self.loaded_count >= self.filtered_count
        ):
            return
        self._start_query(
            offset=self.loaded_count,
            limit=self.PAGE_SIZE,
            context={"kind": "append", "limit": self.PAGE_SIZE},
        )

    def _query_params(self, offset: int, limit: int) -> TransactionQueryParams:
        return TransactionQueryParams(
            user_id=self.user_id,
            group_id=self.group_id,
            period_filter=self.period_filter,
            date_range_filter=self.date_range_filter,
            selected_month=self.selected_month,
            account_filter=self.account_filter,
            category_filter=self.category_filter,
            transaction_type_filter=self.transaction_type_filter,
            needs_review_filter=self.needs_review_filter,
            search=self.search.text(),
            sort_column=self.sort_column,
            sort_descending=self.sort_order == Qt.SortOrder.DescendingOrder,
            offset=offset,
            limit=limit,
        )

    def _start_query(self, offset: int, limit: int, context: dict) -> None:
        self._request_serial += 1
        request_id = self._request_serial
        generation = self._query_generation
        params = self._query_params(offset, limit)
        worker = _TransactionQueryWorker(
            generation,
            request_id,
            params,
            self.query_loader,
            self.session_factory,
        )
        worker.signals.succeeded.connect(self._query_succeeded)
        worker.signals.failed.connect(self._query_failed)
        self._active_workers[request_id] = worker
        self._request_contexts[request_id] = context
        self._set_loading(True)
        self._last_failed_context = None
        self.loading_overlay.show_loading("Loading transactions...")
        logger.debug(
            "Transaction query started (generation=%s, offset=%s)",
            generation,
            offset,
        )
        self._thread_pool.start(worker)

    @Slot(int, int, int, object)
    def _query_succeeded(
        self,
        generation: int,
        request_id: int,
        offset: int,
        result: TransactionQueryResult,
    ) -> None:
        self._active_workers.pop(request_id, None)
        context = self._request_contexts.pop(request_id, {})
        if generation != self._query_generation:
            logger.debug(
                "Transaction query ignored as stale (generation=%s, current=%s)",
                generation,
                self._query_generation,
            )
            return

        logger.debug(
            "Transaction query finished (generation=%s, offset=%s, rows=%s)",
            generation,
            offset,
            len(result.rows),
        )
        self.total_count = result.total_count
        self.filtered_count = result.filtered_count
        self.count_label.setText(
            f"{self.total_count:,} transaction{'s' if self.total_count != 1 else ''}"
        )
        self.count_changed.emit(self.total_count)

        if context.get("kind") == "append":
            if offset != self.loaded_count:
                logger.debug("Transaction page ignored because its offset is stale")
                self._set_loading(False)
                self.loading_overlay.hide_loading()
                return
            self._append_rows(result.rows)
            self.loaded_count += len(result.rows)
            self.range_label.setText(
                f"Showing {self.loaded_count:,} of {self.filtered_count:,} transactions"
            )
            self._set_loading(False)
            self.loading_overlay.hide_loading()
            return

        self._update_filter_options(
            result.accounts,
            result.categories,
            result.available_months,
        )
        self._replace_rows(result, context)
        self._set_loading(False)
        self.loading_overlay.hide_loading()

    def _replace_rows(self, result: TransactionQueryResult, context: dict) -> None:
        vertical_scrollbar = self.table.verticalScrollBar()
        horizontal_scrollbar = self.table.horizontalScrollBar()
        for row in self.rows:
            row.deleteLater()
        self.rows = []
        self.loaded_count = 0
        self.table.setRowCount(0)
        vertical_scrollbar.setValue(0)
        self._append_rows(result.rows)
        self.loaded_count = len(result.rows)
        self.range_label.setText(
            f"Showing {self.loaded_count:,} of {self.filtered_count:,} transactions"
        )
        if self.filtered_count:
            self.message.hide()
        else:
            if self.total_count == 0:
                empty_text = (
                    "No removed transactions"
                    if self.category_filter == "deleted"
                    else "No active transactions. Use Removed Transactions to restore items."
                )
            else:
                empty_text = "No transactions match your search or filter"
            self.message.setText(empty_text)
            self.message.show()
        if context.get("preserve_scroll"):
            vertical_scrollbar.setValue(min(
                context.get("scroll_position", 0),
                vertical_scrollbar.maximum(),
            ))
            horizontal_scrollbar.setValue(context.get("horizontal_position", 0))

    @Slot(int, int, int, object)
    def _query_failed(
        self,
        generation: int,
        request_id: int,
        offset: int,
        _exception: Exception,
    ) -> None:
        self._active_workers.pop(request_id, None)
        context = self._request_contexts.pop(request_id, {})
        if generation != self._query_generation:
            logger.debug(
                "Failed transaction query ignored as stale (generation=%s, current=%s)",
                generation,
                self._query_generation,
            )
            return
        self._set_loading(False)
        self._last_failed_context = {**context, "offset": offset}
        self.loading_overlay.show_error("Could not load transactions.")

    def _retry_failed_query(self) -> None:
        context = self._last_failed_context
        if context is None or (self.user_id is None and self.group_id is None):
            return
        self._last_failed_context = None
        if context.get("kind") == "append":
            self._start_query(
                offset=context.get("offset", self.loaded_count),
                limit=context.get("limit", self.PAGE_SIZE),
                context=context,
            )
        else:
            self._apply_filters(bool(context.get("preserve_scroll")))

    def _show_empty_table(self) -> None:
        self.total_count = 0
        self.filtered_count = 0
        self.loaded_count = 0
        for row in self.rows:
            row.deleteLater()
        self.rows = []
        self.table.setRowCount(0)
        self.count_label.setText("0 transactions")
        self.count_changed.emit(0)
        self.range_label.setText("Showing 0 transactions")
        self.message.setText("No transactions yet")
        self.message.show()

    def _append_rows(self, transactions) -> None:
        new_rows = []
        for transaction in transactions:
            row = TransactionRow(
                transaction.id,
                transaction.transaction_date,
                transaction.description,
                transaction.amount,
                transaction.transaction_type,
                transaction.imported_at,
                transaction.category_id,
                transaction.account_name,
                transaction.institution,
                transaction.is_deleted,
                self.category_options,
                parent=self,
            )
            row.category_changed.connect(
                lambda transaction_id, _category_id, row=row:
                self._save_assignment(row, transaction_id)
            )
            row.transaction_type_changed.connect(
                lambda transaction_id, _transaction_type, row=row:
                self._save_assignment(row, transaction_id)
            )
            row.deletion_changed.connect(self._set_deleted)
            row.create_rule_requested.connect(self._request_rule)
            new_rows.append(row)

        self.table.setUpdatesEnabled(False)
        try:
            self.table.append_rows([row.cells for row in new_rows])
        finally:
            self.table.setUpdatesEnabled(True)
        self.rows.extend(new_rows)

    def _request_rule(self, transaction_id: int) -> None:
        if self.group_id is not None:
            QMessageBox.information(
                self,
                "Personal Rules",
                "Classification rules belong to individual users. Switch to the "
                "account owner's personal profile to create a rule.",
            )
            return
        try:
            with self.session_factory() as session:
                transaction = get_visible_transaction(
                    session, transaction_id, user_id=self.user_id
                )
                if transaction is None:
                    raise ValueError("Transaction is no longer available")
                prefill = rule_prefill_from_transaction(transaction)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not create rule:\n{exc}")
            return
        self.create_rule_requested.emit(prefill)

    def _save_assignment(
        self,
        row: TransactionRow,
        transaction_id: int,
    ) -> None:
        transaction_type = row.transaction_type_combo.currentData()
        category_id = row.category_combo.currentData()
        if transaction_type in CATEGORY_FREE_TRANSACTION_TYPES:
            category_id = None
            with QSignalBlocker(row.category_combo):
                row.category_combo.setCurrentIndex(0)
            row._style_category()
        try:
            with self.session_factory.begin() as session:
                transaction = get_visible_transaction(
                    session,
                    transaction_id,
                    user_id=self.user_id,
                    group_id=self.group_id,
                )
                if transaction is None:
                    raise ValueError("Transaction is no longer available")
                if category_id is not None and session.get(Category, category_id) is None:
                    raise ValueError("Category is no longer available")
                transaction.transaction_type = transaction_type
                transaction.category_id = category_id
                transaction.classification_source = ClassificationSource.MANUAL.value
        except Exception as exc:
            row.restore_assignment()
            self.message.setText(f"Could not save transaction assignment: {exc}")
            self.message.show()
            return

        row.mark_saved(transaction_type, category_id)
        QTimer.singleShot(0, lambda: self._apply_filters(preserve_scroll=True))

    def _set_deleted(self, transaction_id: int, deleted: bool) -> None:
        try:
            set_transaction_deleted(
                transaction_id,
                self.user_id,
                deleted,
                self.session_factory,
                group_id=self.group_id,
            )
        except Exception as exc:
            self.message.setText(f"Could not update transaction: {exc}")
            self.message.show()
            return

        QTimer.singleShot(0, lambda: self._apply_filters(preserve_scroll=True))
