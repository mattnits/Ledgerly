from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.models import Account, Group, User
from app.services.profiles import visible_account_scope
from app.ui.widgets.generic_table import GenericTable
from app.ui.widgets.page_header import PageHeader
from app.ui.widgets.account_badge import AccountBadge


class AccountsPage(QWidget):
    def __init__(self, session_factory=SessionLocal):
        super().__init__()
        self.setObjectName("accountsPage")
        self.session_factory = session_factory
        self.user_id: str | None = None
        self.group_id: int | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(18)

        layout.addWidget(PageHeader("Accounts"))

        self.empty_label = QLabel("No accounts yet")
        self.empty_label.setObjectName("emptyLabel")
        layout.addWidget(self.empty_label)

        self.table = GenericTable((
            "Account", "Institution", "Type", "Owner", "Balance", "Balance as of",
        ))
        card = QFrame()
        card.setObjectName("contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.addWidget(self.table)
        layout.addWidget(card, 1)

    def reload(self) -> None:
        if self.user_id is None and self.group_id is None:
            self.table.set_rows([])
            self.empty_label.setVisible(True)
            return
        with self.session_factory() as session:
            accounts = session.execute(
                select(
                    Account.name,
                    Account.institution,
                    Account.account_type,
                    Account.balance,
                    Account.balance_as_of,
                    User.name,
                    Group.name,
                )
                .outerjoin(User, Account.user_id == User.id)
                .outerjoin(Group, Account.group_id == Group.id)
                .where(visible_account_scope(self.user_id, self.group_id))
                .order_by(Account.name, Account.id)
            ).all()

        rows = []
        for name, institution, account_type, balance, balance_as_of, user_name, group_name in accounts:
            if balance is None:
                balance_text = "—"
            elif balance < 0:
                balance_text = f"-${abs(balance):,.2f}"
            else:
                balance_text = f"${balance:,.2f}"
            owner = f"User: {user_name}" if user_name else f"Group: {group_name}"
            rows.append((
                AccountBadge(name, institution),
                institution,
                account_type.title(),
                owner,
                balance_text,
                balance_as_of.isoformat() if balance_as_of else "—",
            ))

        self.table.set_rows(rows)
        self.empty_label.setVisible(not rows)

    def set_profile(
        self,
        *,
        user_id: str | None = None,
        group_id: int | None = None,
        reload: bool = True,
    ) -> None:
        self.user_id = user_id
        self.group_id = group_id
        if reload:
            self.reload()

    def set_user_id(self, user_id: str | None) -> None:
        self.set_profile(user_id=user_id)
