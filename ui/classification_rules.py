from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from database.category_rules import (
    RulePrefill,
    RuleSummary,
    apply_rule_to_existing_transactions,
    count_transactions_matching_rule,
    delete_category_rule,
    list_category_rules,
    save_category_rule,
)
from database.db import SessionLocal
from database.models import Category
from ui.components.generic_dialog import GenericDialog
from ui.theme import set_button_icon
from utils.constants import (
    CATEGORY_FREE_TRANSACTION_TYPES,
    INCOME_CATEGORY_NAMES,
    TRANSACTION_TYPE_LABELS,
    MatchType,
    TransactionType,
)


MATCH_TYPE_LABELS = {
    MatchType.CONTAINS: "Contains",
    MatchType.STARTS_WITH: "Starts with",
    MatchType.EXACT: "Exact",
}


class ClassificationRulesDialog(QDialog):
    rules_changed = Signal()

    def __init__(
        self,
        user_id: str,
        parent=None,
        session_factory=SessionLocal,
        prefill: RulePrefill | None = None,
    ):
        super().__init__(parent)
        self.user_id = user_id
        self.session_factory = session_factory
        self.rules: list[RuleSummary] = []
        self.setWindowTitle("Classification Rules")
        self.resize(920, 520)
        self.setObjectName("classificationRulesDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)
        description = QLabel(
            "The highest-priority active matching rule assigns the transaction type "
            "and optional category. Priority ties prefer Exact, then Starts with, "
            "then Contains; longer patterns and older rules break remaining ties. "
            "Manual classifications are protected."
        )
        description.setObjectName("mutedLabel")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.table = QTableWidget(0, 6)
        self.table.setObjectName("rulesTable")
        self.table.setHorizontalHeaderLabels((
            "Keyword / Pattern", "Match Type", "Transaction Type",
            "Category", "Priority", "Active",
        ))
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setFixedHeight(46)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.doubleClicked.connect(self._edit_selected)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        add_button = QPushButton("Add Rule")
        add_button.setObjectName("primaryButton")
        edit_button = QPushButton("Edit Selected")
        edit_button.setObjectName("secondaryActionButton")
        delete_button = QPushButton("Delete Selected")
        delete_button.setObjectName("dangerButton")
        close_button = QPushButton("Close")
        set_button_icon(
            add_button, "fa6s.plus", color="#ffffff", active_color="#ffffff"
        )
        set_button_icon(edit_button, "fa6s.pen", color="#b9bec5")
        set_button_icon(delete_button, "fa6s.trash", color="#ff9da0")
        set_button_icon(close_button, "fa6s.xmark", size=15)
        add_button.clicked.connect(lambda: self._open_editor())
        edit_button.clicked.connect(self._edit_selected)
        delete_button.clicked.connect(self._delete_selected)
        close_button.clicked.connect(self.accept)
        buttons.addWidget(add_button)
        buttons.addWidget(edit_button)
        buttons.addWidget(delete_button)
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        self.reload()
        if prefill is not None:
            QTimer.singleShot(0, lambda: self._open_editor(prefill=prefill))

    def reload(self) -> None:
        with self.session_factory() as session:
            self.rules = list_category_rules(session, self.user_id)
        self.table.setRowCount(0)
        for rule in self.rules:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (
                rule.pattern,
                MATCH_TYPE_LABELS[rule.match_type],
                (
                    TRANSACTION_TYPE_LABELS[rule.transaction_type]
                    if rule.transaction_type is not None
                    else "Not set (legacy rule)"
                ),
                rule.category_name or "—",
                str(rule.priority),
                "Yes" if rule.is_active else "No",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, rule.id)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def _selected_rule(self) -> RuleSummary | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        rule_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        return next((rule for rule in self.rules if rule.id == rule_id), None)

    def _edit_selected(self, *_args) -> None:
        rule = self._selected_rule()
        if rule is None:
            QMessageBox.information(self, "Classification Rules", "Select a rule first.")
            return
        self._open_editor(rule)

    def _delete_selected(self) -> None:
        rule = self._selected_rule()
        if rule is None:
            QMessageBox.information(self, "Classification Rules", "Select a rule first.")
            return
        if QMessageBox.question(
            self,
            "Delete Classification Rule",
            f"Delete the rule for '{rule.pattern}'?",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            with self.session_factory.begin() as session:
                delete_category_rule(session, self.user_id, rule.id)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not delete rule:\n{exc}")
            return
        self.reload()
        self.rules_changed.emit()

    def _open_editor(
        self,
        rule: RuleSummary | None = None,
        *,
        prefill: RulePrefill | None = None,
    ) -> None:
        with self.session_factory() as session:
            categories = list(session.execute(
                select(Category.id, Category.name).order_by(Category.name)
            ))

        content = QWidget()
        layout = QVBoxLayout(content)
        pattern = rule.pattern if rule else prefill.pattern.upper() if prefill else ""
        pattern_input = QLineEdit(pattern)
        pattern_input.setMaxLength(255)
        layout.addWidget(QLabel("Keyword / Pattern"))
        layout.addWidget(pattern_input)

        match_type_input = QComboBox()
        for match_type, label in MATCH_TYPE_LABELS.items():
            match_type_input.addItem(label, match_type)
        match_type_input.setCurrentIndex(match_type_input.findData(
            rule.match_type
            if rule
            else prefill.match_type
            if prefill
            else MatchType.CONTAINS
        ))
        layout.addWidget(QLabel("Match Type"))
        layout.addWidget(match_type_input)

        transaction_type_input = QComboBox()
        if rule is not None and rule.transaction_type is None:
            transaction_type_input.addItem("Not set (legacy rule)", None)
        for transaction_type, label in TRANSACTION_TYPE_LABELS.items():
            transaction_type_input.addItem(label, transaction_type)
        selected_type = (
            rule.transaction_type
            if rule
            else prefill.transaction_type
            if prefill and prefill.transaction_type is not None
            else TransactionType.EXPENSE
        )
        transaction_type_input.setCurrentIndex(
            transaction_type_input.findData(selected_type)
        )
        layout.addWidget(QLabel("Transaction Type"))
        layout.addWidget(transaction_type_input)

        category_input = QComboBox()
        layout.addWidget(QLabel("Category"))
        layout.addWidget(category_input)
        category_initialized = False

        def refresh_categories() -> None:
            nonlocal category_initialized
            previous = (
                category_input.currentData()
                if category_initialized
                else rule.category_id
                if rule is not None
                else prefill.category_id
                if prefill is not None
                else None
            )
            transaction_type = transaction_type_input.currentData()
            category_input.clear()
            category_input.addItem("None", None)
            if transaction_type in CATEGORY_FREE_TRANSACTION_TYPES:
                category_input.setEnabled(False)
                category_initialized = True
                return
            for category_id, name in categories:
                if (
                    transaction_type == TransactionType.INCOME
                    and name not in INCOME_CATEGORY_NAMES
                ):
                    continue
                if (
                    transaction_type == TransactionType.EXPENSE
                    and name in INCOME_CATEGORY_NAMES
                ):
                    continue
                category_input.addItem(name, category_id)
            category_input.setCurrentIndex(max(0, category_input.findData(previous)))
            category_input.setEnabled(True)
            category_initialized = True

        transaction_type_input.currentIndexChanged.connect(refresh_categories)
        refresh_categories()

        priority_input = QSpinBox()
        priority_input.setRange(-100000, 100000)
        priority_input.setValue(rule.priority if rule else 0)
        layout.addWidget(QLabel("Priority (higher wins)"))
        layout.addWidget(priority_input)

        active_input = QCheckBox("Active")
        active_input.setChecked(rule.is_active if rule else True)
        apply_input = QCheckBox("Apply to existing matching transactions")
        layout.addWidget(active_input)
        layout.addWidget(apply_input)

        dialog = GenericDialog(
            "Edit Classification Rule" if rule else "Add Classification Rule",
            content,
            self,
        )

        def update_match_count() -> None:
            try:
                with self.session_factory() as session:
                    count = count_transactions_matching_rule(
                        session,
                        self.user_id,
                        pattern_input.text(),
                        match_type_input.currentData(),
                    )
            except Exception:
                apply_input.setText("Apply to existing matching transactions")
                return
            apply_input.setText(
                f"Apply to {count} eligible existing matching transaction(s)"
            )

        match_count_timer = QTimer(dialog)
        match_count_timer.setSingleShot(True)
        match_count_timer.setInterval(200)
        match_count_timer.timeout.connect(update_match_count)
        pattern_input.textChanged.connect(lambda *_args: match_count_timer.start())
        match_type_input.currentIndexChanged.connect(
            lambda *_args: match_count_timer.start()
        )
        update_match_count()

        def submit() -> None:
            transaction_type = transaction_type_input.currentData()
            if rule is None and transaction_type is None:
                QMessageBox.warning(
                    dialog, "Invalid Rule", "Select a transaction type."
                )
                return
            try:
                with self.session_factory.begin() as session:
                    saved_rule = save_category_rule(
                        session,
                        self.user_id,
                        pattern_input.text(),
                        transaction_type,
                        category_input.currentData(),
                        match_type=match_type_input.currentData(),
                        priority=priority_input.value(),
                        is_active=active_input.isChecked(),
                        rule_id=rule.id if rule else None,
                    )
                    updated = 0
                    if apply_input.isChecked():
                        updated = apply_rule_to_existing_transactions(
                            session, self.user_id, saved_rule
                        )
            except Exception as exc:
                QMessageBox.critical(dialog, "Error", f"Could not save rule:\n{exc}")
                return
            dialog.accept()
            self.reload()
            self.rules_changed.emit()
            if apply_input.isChecked():
                QMessageBox.information(
                    self,
                    "Classification Rule",
                    f"Updated {updated} existing matching transaction(s).",
                )

        dialog.submitted.connect(submit)
        dialog.exec()
