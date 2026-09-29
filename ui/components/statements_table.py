from datetime import date

from PySide6.QtCore import Qt, QSignalBlocker, QTimer, Signal
from PySide6.QtWidgets import (
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
from sqlalchemy import String, and_, cast, func, or_, select

from database.db import SessionLocal
from database.category_rules import (
    needs_review_expression,
    normalize_description,
    rule_prefill_from_transaction,
)
from database.models import Account, Category, Transaction
from database.transactions import get_transaction_months, set_transaction_deleted
from ui.components.generic_table import GenericTable
from ui.components.period_selector import PeriodSelector
from ui.components.transaction_row import TransactionRow
from utils.constants import (
    CATEGORY_FREE_TRANSACTION_TYPES,
    ClassificationSource,
    TRANSACTION_TYPE_LABELS,
    TransactionType,
)


class StatementsTable(QWidget):
    create_rule_requested = Signal(object)

    PAGE_SIZE = 200
    COLUMN_HEADERS = (
        "Date", "Description", "Amount", "Account", "Transaction Type",
        "Category", "Imported At", "Action",
    )

    def __init__(self, parent=None, session_factory=SessionLocal):
        super().__init__(parent)
        self.session_factory = session_factory
        self.user_id: str | None = None
        self.rows: list[TransactionRow] = []
        self.category_options: list[tuple[int, str, str]] = []
        self.total_count = 0
        self.filtered_count = 0
        self.loaded_count = 0
        self._loading = False
        self._query = None
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

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(12)

        toolbar = QWidget()
        toolbar.setObjectName("transactionsToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(12)

        self.period_selector = PeriodSelector()
        self.period_selector.selection_changed.connect(self._select_period)
        toolbar_layout.addWidget(self.period_selector)
        self.monthly_button = self.period_selector.monthly_button
        self.all_time_button = self.period_selector.all_time_button
        self.month_selector = self.period_selector.month_selector

        self.count_label = QLabel("0 transactions")
        self.count_label.setObjectName("transactionsCount")
        toolbar_layout.addWidget(self.count_label)
        self.review_mode_label = QLabel("Needs Review mode")
        self.review_mode_label.setObjectName("reviewModeLabel")
        self.review_mode_label.hide()
        toolbar_layout.addWidget(self.review_mode_label)
        toolbar_layout.addStretch()

        self.search = QLineEdit()
        self.search.setObjectName("transactionSearch")
        self.search.setPlaceholderText("Search transactions...")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(290)
        self.search.textChanged.connect(self._reset_and_apply)
        toolbar_layout.addWidget(self.search)

        outer_layout.addWidget(toolbar)

        filter_bar = QFrame()
        filter_bar.setObjectName("filterBar")
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(14, 10, 14, 10)
        filter_layout.setSpacing(16)

        self.account_selector = QComboBox()
        self.account_selector.addItem("All Accounts", "all")
        self.account_selector.currentIndexChanged.connect(self._select_account)
        self._add_filter_field(filter_layout, "Account", self.account_selector)

        self.category_selector = QComboBox()
        self.category_selector.addItem("All Categories", "all")
        self.category_selector.currentIndexChanged.connect(self._select_category)
        self._add_filter_field(filter_layout, "Category", self.category_selector)

        self.transaction_type_selector = QComboBox()
        self.transaction_type_selector.addItem("All Transaction Types", "all")
        for transaction_type, label in TRANSACTION_TYPE_LABELS.items():
            self.transaction_type_selector.addItem(label, transaction_type)
        self.transaction_type_selector.currentIndexChanged.connect(
            self._select_transaction_type
        )
        self._add_filter_field(
            filter_layout, "Transaction Type", self.transaction_type_selector
        )

        self.needs_review_checkbox = QCheckBox("Needs Review only")
        self.needs_review_checkbox.setObjectName("needsReviewFilter")
        self.needs_review_checkbox.toggled.connect(self._select_needs_review)
        filter_layout.addWidget(self.needs_review_checkbox)

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
        outer_layout.addWidget(card)
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
        for column, width in (
            (0, 118),
            (2, 100),
            (3, 115),
            (4, 155),
            (5, 170),
            (6, 138),
            (7, 76),
        ):
            table_header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
        table_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeaderItem(2).setTextAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self._update_sort_headers()
        card_layout.addWidget(self.table, 1)

        self.message = QLabel("No transactions yet")
        self.message.setObjectName("transactionsMessage")
        self.message.hide()
        card_layout.addWidget(self.message)

        footer = QWidget()
        footer.setObjectName("transactionsFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 12, 24, 12)
        footer_layout.setSpacing(6)
        self.range_label = QLabel("Showing 0 transactions")
        self.range_label.setObjectName("transactionsRange")
        footer_layout.addWidget(self.range_label)
        footer_layout.addStretch()

        card_layout.addWidget(footer)

        self.setStyleSheet("""
            QFrame#transactionsCard {
                background: #1f2329;
                border: 1px solid #353b44;
                border-radius: 16px;
            }
            QWidget#transactionsFooter {
                background: #222730;
                border-bottom-left-radius: 16px;
                border-bottom-right-radius: 16px;
            }
            QLabel#transactionsCount, QLabel#transactionsRange,
            QLabel#transactionsMessage {
                color: #b6c0ce;
                font-size: 13px;
            }
            QLabel#transactionsCount { padding-left: 10px; }
            QLabel#reviewModeLabel {
                color: #ffd68a;
                background: #4a3517;
                border: 1px solid #7b5822;
                border-radius: 8px;
                padding: 4px 9px;
            }
            QLabel#transactionsMessage { padding: 10px 24px; }
            QLineEdit#transactionSearch {
                color: #e3eaf4;
                background: #1e2228;
                border: 1px solid #3b424d;
                border-radius: 10px;
                padding: 9px 13px;
                font-size: 14px;
            }
            QLineEdit#transactionSearch:focus { border-color: #5a9fea; }
            QFrame#filterBar {
                background: #1d232b;
                border: 1px solid #38414d;
                border-radius: 12px;
            }
            QLabel#filterLabel {
                color: #cbd4e1;
                font-size: 11px;
            }
            QComboBox#filterCombo {
                color: #e3eaf4;
                background: #1a2028;
                border: 1px solid #3b4552;
                border-radius: 8px;
                padding: 7px 30px 7px 12px;
                min-height: 20px;
            }
            QComboBox#filterCombo::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border: none;
                background: transparent;
            }
            QComboBox#filterCombo QAbstractItemView {
                color: #e3eaf4;
                background: #232a33;
                border: 1px solid #414955;
                selection-background-color: #304b6b;
            }
            QFrame#filterDivider { color: #38414d; }
            QCheckBox#needsReviewFilter {
                color: #d7e0ec;
                spacing: 7px;
                padding: 8px;
            }
            QPushButton#clearFiltersButton {
                color: #8ba8ff;
                background: transparent;
                border: none;
                padding: 8px 10px;
            }
            QPushButton#clearFiltersButton:hover { color: #bdcbff; }
        """)
        self._apply_filters()

    @staticmethod
    def _add_filter_field(layout: QHBoxLayout, label: str, selector: QComboBox) -> None:
        field = QWidget()
        field_layout = QVBoxLayout(field)
        field_layout.setContentsMargins(0, 0, 0, 0)
        field_layout.setSpacing(3)
        title = QLabel(label)
        title.setObjectName("filterLabel")
        selector.setObjectName("filterCombo")
        field_layout.addWidget(title)
        field_layout.addWidget(selector)
        layout.addWidget(field, 1)

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
        self.user_id = user_id
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
        if self.user_id is None:
            self.category_options = []
            accounts = []
        else:
            with self.session_factory() as session:
                accounts = session.execute(
                    select(Account.id, Account.name, Account.institution)
                    .where(Account.user_id == self.user_id)
                    .order_by(Account.name, Account.id)
                ).all()
                self.category_options = list(session.execute(
                    select(Category.id, Category.name, Category.color).order_by(Category.name)
                ).all())
        self.available_months = get_transaction_months(
            self.user_id, self.session_factory, include_deleted=True
        )
        self._refresh_month_choices()
        with QSignalBlocker(self.account_selector):
            self.account_selector.clear()
            self.account_selector.addItem("All Accounts", "all")
            for account_id, name, institution in accounts:
                self.account_selector.addItem(f"{name} ({institution})", account_id)
            selected = self.account_selector.findData(self.account_filter)
            if selected < 0:
                self.account_filter = "all"
                selected = 0
            self.account_selector.setCurrentIndex(selected)
        with QSignalBlocker(self.category_selector):
            self.category_selector.clear()
            self.category_selector.addItem("All Categories", "all")
            self.category_selector.addItem("Removed Transactions", "deleted")
            self.category_selector.addItem("Uncategorized", None)
            for category_id, name, _ in self.category_options:
                self.category_selector.addItem(name, category_id)
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
        self._apply_filters()

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
        vertical_scrollbar = self.table.verticalScrollBar()
        horizontal_scrollbar = self.table.horizontalScrollBar()
        scroll_position = vertical_scrollbar.value() if preserve_scroll else 0
        horizontal_position = horizontal_scrollbar.value() if preserve_scroll else 0
        previously_loaded = self.loaded_count if preserve_scroll else 0
        self._query = None
        self.total_count = 0
        self.filtered_count = 0
        if self.user_id is not None:
            base = (
                select(
                    Transaction.id,
                    Transaction.transaction_date,
                    Transaction.description,
                    Transaction.amount,
                    Transaction.transaction_type,
                    Transaction.imported_at,
                    Transaction.category_id,
                    Account.name,
                    Transaction.is_deleted,
                )
                .join(Account, Transaction.account_id == Account.id)
                .outerjoin(Category, Transaction.category_id == Category.id)
                .where(Account.user_id == self.user_id)
            )
            base = base.where(
                Transaction.is_deleted.is_(self.category_filter == "deleted")
            )
            if self.period_filter == "monthly":
                year, month = self.selected_month
                first_day = date(year, month, 1)
                next_month = date(year + (month == 12), month % 12 + 1, 1)
                base = base.where(
                    Transaction.transaction_date >= first_day,
                    Transaction.transaction_date < next_month,
                )
            elif self.date_range_filter == "this_year":
                year = date.today().year
                base = base.where(
                    Transaction.transaction_date >= date(year, 1, 1),
                    Transaction.transaction_date < date(year + 1, 1, 1),
                )

            with self.session_factory() as session:
                self.total_count = session.scalar(
                    select(func.count()).select_from(base.order_by(None).subquery())
                ) or 0

            if self.account_filter != "all":
                base = base.where(Account.id == self.account_filter)

            if self.needs_review_filter:
                base = base.where(needs_review_expression())
            if self.category_filter not in ("all", "deleted"):
                base = base.where(Transaction.category_id == self.category_filter)

            if self.transaction_type_filter != "all":
                base = base.where(
                    Transaction.transaction_type == self.transaction_type_filter
                )

            query = self.search.text().strip()
            if query:
                pattern = f"%{query}%"
                description_tokens = normalize_description(query).split()
                search_terms = [
                    Transaction.description.ilike(pattern),
                    Account.name.ilike(pattern),
                    Category.name.ilike(pattern),
                    cast(Transaction.transaction_type, String).ilike(pattern),
                    cast(Transaction.transaction_date, String).ilike(pattern),
                    cast(Transaction.amount, String).ilike(pattern),
                ]
                if description_tokens:
                    search_terms.append(and_(*(
                        Transaction.description.ilike(f"%{token}%")
                        for token in description_tokens
                    )))
                base = base.where(or_(*search_terms))

            sort_expressions = (
                Transaction.transaction_date,
                Transaction.description,
                Transaction.amount,
                Account.name,
                Transaction.transaction_type,
                func.coalesce(Category.name, "Uncategorized"),
                Transaction.imported_at,
            )
            expression = sort_expressions[self.sort_column]
            ordering = (
                expression.desc()
                if self.sort_order == Qt.SortOrder.DescendingOrder
                else expression.asc()
            )
            self._query = base.order_by(ordering, Transaction.id.desc())
            with self.session_factory() as session:
                self.filtered_count = session.scalar(
                    select(func.count()).select_from(base.order_by(None).subquery())
                ) or 0

        self.count_label.setText(
            f"{self.total_count:,} transaction{'s' if self.total_count != 1 else ''}"
        )
        self.review_mode_label.setVisible(self.needs_review_filter)
        for row in self.rows:
            row.deleteLater()
        self.rows = []
        self.loaded_count = 0
        self.table.setRowCount(0)
        vertical_scrollbar.setValue(0)
        self.range_label.setText(f"Showing 0 of {self.filtered_count:,} transactions")
        if self.filtered_count:
            self.message.hide()
            self._load_more()
            while (
                self.loaded_count < previously_loaded
                and self.loaded_count < self.filtered_count
            ):
                self._load_more()
            if preserve_scroll:
                vertical_scrollbar.setValue(min(scroll_position, vertical_scrollbar.maximum()))
                horizontal_scrollbar.setValue(horizontal_position)
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

    def _load_more(self) -> None:
        if self._loading or self._query is None or self.loaded_count >= self.filtered_count:
            return
        self._loading = True
        try:
            with self.session_factory() as session:
                transactions = session.execute(
                    self._query.limit(self.PAGE_SIZE).offset(self.loaded_count)
                ).all()
            if not transactions:
                self.filtered_count = self.loaded_count
                return
            self._append_rows(transactions)
            self.loaded_count += len(transactions)
            self.range_label.setText(
                f"Showing {self.loaded_count:,} of {self.filtered_count:,} transactions"
            )
        finally:
            self._loading = False

    def _append_rows(self, transactions) -> None:
        new_rows = []
        for transaction in transactions:
            row = TransactionRow(
                *transaction,
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
        try:
            with self.session_factory() as session:
                transaction = session.get(Transaction, transaction_id)
                if transaction is None or transaction.account.user_id != self.user_id:
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
                transaction = session.get(Transaction, transaction_id)
                if transaction is None or transaction.account.user_id != self.user_id:
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
                transaction_id, self.user_id, deleted, self.session_factory
            )
        except Exception as exc:
            self.message.setText(f"Could not update transaction: {exc}")
            self.message.show()
            return

        QTimer.singleShot(0, lambda: self._apply_filters(preserve_scroll=True))
