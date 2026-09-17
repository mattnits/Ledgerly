from math import ceil

from PySide6.QtCore import Qt, QSignalBlocker, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import String, cast, func, or_, select

from database.db import SessionLocal
from database.category_rules import categorize_matching_transactions, save_category_rule
from database.models import Account, Category, Transaction
from ui.components.generic_table import GenericTable
from ui.components.transaction_row import TransactionRow


class StatementsTable(QWidget):
    PAGE_SIZE = 10

    def __init__(self, parent=None, session_factory=SessionLocal):
        super().__init__(parent)
        self.session_factory = session_factory
        self.user_id: str | None = None
        self.rows: list[TransactionRow] = []
        self.category_options: list[tuple[int, str]] = []
        self.total_count = 0
        self.current_page = 1
        self.category_filter: int | str | None = "all"

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("transactionsCard")
        outer_layout.addWidget(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("transactionsHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(26, 18, 26, 18)
        header_layout.setSpacing(14)

        heading = QVBoxLayout()
        heading.setSpacing(5)
        title = QLabel("Transactions")
        title.setObjectName("transactionsTitle")
        self.count_label = QLabel("0 transactions")
        self.count_label.setObjectName("transactionsCount")
        heading.addWidget(title)
        heading.addWidget(self.count_label)
        header_layout.addLayout(heading)
        header_layout.addStretch()

        self.search = QLineEdit()
        self.search.setObjectName("transactionSearch")
        self.search.setPlaceholderText("Search transactions...")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(290)
        self.search.textChanged.connect(self._reset_and_apply)
        header_layout.addWidget(self.search)

        self.filter_button = QPushButton("Filter")
        self.filter_button.setObjectName("transactionFilter")
        self.filter_menu = QMenu(self.filter_button)
        self.filter_button.setMenu(self.filter_menu)
        header_layout.addWidget(self.filter_button)
        card_layout.addWidget(header)

        self.table = GenericTable((
            "Date", "Description", "Amount", "Account", "Imported at", "Category",
        ))
        table_header = self.table.horizontalHeader()
        for column, width in ((0, 155), (2, 135), (3, 135), (4, 170), (5, 220)):
            table_header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(column, width)
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

        self.previous_button = QPushButton("‹")
        self.previous_button.setObjectName("pageArrow")
        self.previous_button.clicked.connect(lambda: self._go_to_page(self.current_page - 1))
        footer_layout.addWidget(self.previous_button)

        self.page_buttons_layout = QHBoxLayout()
        self.page_buttons_layout.setSpacing(4)
        footer_layout.addLayout(self.page_buttons_layout)

        self.next_button = QPushButton("›")
        self.next_button.setObjectName("pageArrow")
        self.next_button.clicked.connect(lambda: self._go_to_page(self.current_page + 1))
        footer_layout.addWidget(self.next_button)
        card_layout.addWidget(footer)

        self.setStyleSheet("""
            QFrame#transactionsCard {
                background: #1f2329;
                border: 1px solid #353b44;
                border-radius: 18px;
            }
            QWidget#transactionsHeader, QWidget#transactionsFooter {
                background: #252a31;
            }
            QWidget#transactionsHeader {
                border-top-left-radius: 18px;
                border-top-right-radius: 18px;
            }
            QWidget#transactionsFooter {
                border-bottom-left-radius: 18px;
                border-bottom-right-radius: 18px;
            }
            QLabel#transactionsTitle {
                color: #f5f7fb;
                font-size: 26px;
                font-weight: 700;
            }
            QLabel#transactionsCount, QLabel#transactionsRange,
            QLabel#transactionsMessage {
                color: #b6c0ce;
                font-size: 13px;
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
            QPushButton#transactionFilter, QPushButton#pageArrow,
            QPushButton#pageNumber {
                color: #d8e0eb;
                background: #252a31;
                border: 1px solid #3a414b;
                border-radius: 9px;
                padding: 8px 13px;
                font-size: 13px;
            }
            QPushButton#transactionFilter:hover, QPushButton#pageArrow:hover,
            QPushButton#pageNumber:hover { background: #303844; }
            QPushButton#pageArrow:disabled { color: #697481; border-color: #303741; }
            QPushButton#pageNumber[active="true"] {
                color: #ffffff;
                background: #294669;
                border-color: #4c9af5;
            }
            QMenu {
                color: #d8e0eb;
                background: #23282f;
                border: 1px solid #414955;
                padding: 5px;
            }
            QMenu::item { padding: 7px 24px; border-radius: 5px; }
            QMenu::item:selected { background: #304b6b; }
        """)
        self._build_filter_menu([])
        self._apply_filters()

    def set_user_id(self, user_id: str | None) -> None:
        self.user_id = user_id
        self.current_page = 1
        self.category_filter = "all"
        self.filter_button.setText("Filter")
        with QSignalBlocker(self.search):
            self.search.clear()
        self.reload()

    def reload(self) -> None:
        if self.user_id is None:
            self.category_options = []
            self.total_count = 0
            self._build_filter_menu([])
            self._apply_filters()
            return

        with self.session_factory() as session:
            self.category_options = list(session.execute(
                select(Category.id, Category.name).order_by(Category.name)
            ).all())
            self.total_count = session.scalar(
                select(func.count(Transaction.id))
                .join(Account, Transaction.account_id == Account.id)
                .where(Account.user_id == self.user_id)
            ) or 0

        self._build_filter_menu(self.category_options)
        self._apply_filters()

    def _build_filter_menu(self, categories: list[tuple[int, str]]) -> None:
        self.filter_menu.clear()
        choices = [("All categories", "all"), ("Uncategorized", None)]
        choices.extend((name, category_id) for category_id, name in categories)
        for name, category_id in choices:
            action = self.filter_menu.addAction(name)
            action.triggered.connect(
                lambda checked=False, selected=category_id, label=name:
                self._set_category_filter(selected, label)
            )

    def _set_category_filter(self, category_id: int | str | None, name: str) -> None:
        self.category_filter = category_id
        self.filter_button.setText("Filter" if category_id == "all" else name)
        self._reset_and_apply()

    def _reset_and_apply(self) -> None:
        self.current_page = 1
        self._apply_filters()

    def _go_to_page(self, page: int) -> None:
        self.current_page = page
        self._apply_filters()

    def _apply_filters(self) -> None:
        self.count_label.setText(
            f"{self.total_count:,} transaction{'s' if self.total_count != 1 else ''}"
        )
        if self.user_id is None:
            total = 0
            transactions = []
        else:
            base = (
                select(
                    Transaction.id,
                    Transaction.transaction_date,
                    Transaction.description,
                    Transaction.amount,
                    Transaction.imported_at,
                    Transaction.category_id,
                    Account.name,
                )
                .join(Account, Transaction.account_id == Account.id)
                .outerjoin(Category, Transaction.category_id == Category.id)
                .where(Account.user_id == self.user_id)
            )
            if self.category_filter != "all":
                base = base.where(Transaction.category_id == self.category_filter)

            query = self.search.text().strip()
            if query:
                pattern = f"%{query}%"
                base = base.where(or_(
                    Transaction.description.ilike(pattern),
                    Account.name.ilike(pattern),
                    Category.name.ilike(pattern),
                    cast(Transaction.transaction_date, String).ilike(pattern),
                    cast(Transaction.amount, String).ilike(pattern),
                ))

            with self.session_factory() as session:
                total = session.scalar(
                    select(func.count()).select_from(base.order_by(None).subquery())
                ) or 0
                total_pages = max(1, ceil(total / self.PAGE_SIZE))
                self.current_page = min(max(self.current_page, 1), total_pages)
                start = (self.current_page - 1) * self.PAGE_SIZE
                transactions = session.execute(
                    base.order_by(
                        Transaction.transaction_date.desc(),
                        Transaction.imported_at.desc(),
                        Transaction.id.desc(),
                    )
                    .limit(self.PAGE_SIZE)
                    .offset(start)
                ).all()

        total_pages = max(1, ceil(total / self.PAGE_SIZE))
        self.current_page = min(max(self.current_page, 1), total_pages)
        start = (self.current_page - 1) * self.PAGE_SIZE
        self._show_rows(transactions)

        if total:
            self.range_label.setText(
                f"Showing {start + 1}–{min(start + self.PAGE_SIZE, total)} of {total:,} transactions"
            )
            self.message.hide()
        else:
            self.range_label.setText("Showing 0 transactions")
            self.message.setText(
                "No transactions yet" if self.total_count == 0 else "No transactions match your search or filter"
            )
            self.message.show()

        self.previous_button.setEnabled(self.current_page > 1)
        self.next_button.setEnabled(self.current_page < total_pages)
        self._render_page_buttons(total_pages)

    def _show_rows(self, transactions) -> None:
        for row in self.rows:
            row.deleteLater()
        self.rows = []
        for transaction in transactions:
            row = TransactionRow(*transaction, self.category_options, parent=self)
            row.category_changed.connect(
                lambda transaction_id, category_id, row=row:
                self._save_category(row, transaction_id, category_id)
            )
            self.rows.append(row)

        self.table.set_rows([row.cells for row in self.rows])
        for row_number, row in enumerate(self.rows):
            amount_item = self.table.item(row_number, 2)
            amount_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            amount_item.setForeground(QColor(
                "#fb7977" if row.amount < 0 else "#63dba0" if row.amount > 0 else "#cbd4e1"
            ))
            self.table.item(row_number, 4).setForeground(QColor("#9eabba"))

    def _render_page_buttons(self, total_pages: int) -> None:
        while self.page_buttons_layout.count():
            item = self.page_buttons_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        pages = sorted({
            page for page in (
                1, total_pages, self.current_page - 1,
                self.current_page, self.current_page + 1,
            ) if 1 <= page <= total_pages
        })
        previous = 0
        for page in pages:
            if page - previous > 1:
                dots = QLabel("…")
                dots.setStyleSheet("color: #aab4c2; padding: 0 5px;")
                self.page_buttons_layout.addWidget(dots)
            button = QPushButton(str(page))
            button.setObjectName("pageNumber")
            button.setProperty("active", page == self.current_page)
            button.clicked.connect(lambda checked=False, selected=page: self._go_to_page(selected))
            self.page_buttons_layout.addWidget(button)
            previous = page

    def _save_category(
        self,
        row: TransactionRow,
        transaction_id: int,
        category_id: int | None,
    ) -> None:
        try:
            with self.session_factory.begin() as session:
                transaction = session.get(Transaction, transaction_id)
                if transaction is None or transaction.account.user_id != self.user_id:
                    raise ValueError("Transaction is no longer available")
                if category_id is not None and session.get(Category, category_id) is None:
                    raise ValueError("Category is no longer available")
                transaction.category_id = category_id
                save_category_rule(
                    session, self.user_id, transaction.description, category_id
                )
                categorize_matching_transactions(
                    session, self.user_id, transaction.description, category_id
                )
        except Exception as exc:
            row.restore_category()
            self.message.setText(f"Could not save category: {exc}")
            self.message.show()
            return

        row.mark_saved(category_id)
        QTimer.singleShot(0, self._apply_filters)
