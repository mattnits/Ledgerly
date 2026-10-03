import os
import unittest
from datetime import date
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QDialog
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.dashboard import get_dashboard_data
from database.db import Base, _migrate_group_color, get_profiles
from database.groups import create_group, remove_membership, update_group
from database.models import (
    Account,
    Category,
    Group,
    GroupMembership,
    Transaction,
    User,
)
from database.profiles import ProfileContext, ProfileType
from database.transactions import TransactionQueryParams, fetch_transactions
from ui.add_user import AddUserDialog
from ui.switch_user import SwitchUserDialog
from utils.constants import TransactionType


class GroupFeatureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.sessions = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        with self.sessions.begin() as session:
            session.add_all((
                User(id="matt", name="Matt", color="#3397f5"),
                User(id="alyssa", name="Alyssa", color="#ef4a8b"),
                User(id="chris", name="Chris", color="#57c978"),
            ))

    def tearDown(self):
        self.engine.dispose()

    def _group_with_accounts(self) -> int:
        group_id = create_group(
            "Household",
            "#9148e8",
            ("matt", "alyssa"),
            session_factory=self.sessions,
        )
        with self.sessions.begin() as session:
            session.add_all((
                Account(
                    id=1, user_id="matt", name="TD Debit",
                    institution="TD", account_type="debit",
                ),
                Account(
                    id=2, user_id="alyssa", name="RBC Visa",
                    institution="RBC", account_type="credit",
                ),
                Account(
                    id=3, group_id=group_id, name="Joint Mastercard",
                    institution="Amex", account_type="credit",
                ),
                Account(
                    id=4, user_id="chris", name="Outside",
                    institution="Other", account_type="debit",
                ),
            ))
        return group_id

    def test_create_group_is_atomic_and_deduplicates_member_ids(self):
        group_id = create_group(
            " Household ",
            "#9148e8",
            ("matt", "alyssa", "matt"),
            session_factory=self.sessions,
        )
        with self.sessions() as session:
            group = session.get(Group, group_id)
            self.assertEqual((group.name, group.color), ("Household", "#9148e8"))
            self.assertEqual(
                set(session.scalars(select(GroupMembership.user_id))),
                {"matt", "alyssa"},
            )

        with self.assertRaises(ValueError):
            create_group(
                "Broken", "#3397f5", ("matt", "missing"),
                session_factory=self.sessions,
            )
        with self.sessions() as session:
            self.assertEqual(
                session.scalar(select(func.count(Group.id)).where(Group.name == "Broken")),
                0,
            )

    def test_database_unique_constraint_prevents_duplicate_membership(self):
        group_id = create_group(
            "Household", "#3397f5", ("matt",), session_factory=self.sessions
        )
        with self.assertRaises(IntegrityError):
            with self.sessions.begin() as session:
                session.add(GroupMembership(group_id=group_id, user_id="matt"))

    def test_group_colour_migration_preserves_existing_rows(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE groups ("
                "id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, "
                "created_at DATETIME NOT NULL)"
            ))
            connection.execute(text(
                "INSERT INTO groups (id, name, created_at) "
                "VALUES (1, 'Existing', '2026-01-01 00:00:00')"
            ))
        _migrate_group_color(engine)
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT id, name, color FROM groups")
            ).one()
        self.assertEqual(tuple(row), (1, "Existing", "#3397f5"))
        engine.dispose()

    def test_membership_updates_change_visibility_without_deleting_users(self):
        group_id = self._group_with_accounts()
        with self.sessions.begin() as session:
            session.add_all((
                Transaction(
                    account_id=1, transaction_date=date(2026, 9, 1),
                    description="Matt", amount=Decimal("10"),
                ),
                Transaction(
                    account_id=2, transaction_date=date(2026, 9, 2),
                    description="Alyssa", amount=Decimal("20"),
                ),
                Transaction(
                    account_id=4, transaction_date=date(2026, 9, 3),
                    description="Chris", amount=Decimal("30"),
                ),
            ))

        def descriptions():
            result = fetch_transactions(
                TransactionQueryParams(
                    user_id=None,
                    group_id=group_id,
                    selected_month=(2026, 9),
                ),
                self.sessions,
            )
            return {row.description for row in result.rows}

        self.assertEqual(descriptions(), {"Matt", "Alyssa"})
        update_group(
            group_id, "Household", "#9148e8", ("matt", "chris"),
            session_factory=self.sessions,
        )
        self.assertEqual(descriptions(), {"Matt", "Chris"})
        remove_membership(group_id, "matt", session_factory=self.sessions)
        with self.sessions() as session:
            self.assertIsNotNone(session.get(User, "matt"))
            self.assertIsNotNone(session.get(Account, 1))

    def test_group_transactions_include_members_and_joint_once(self):
        group_id = self._group_with_accounts()
        with self.sessions.begin() as session:
            for account_id, description in (
                (1, "Matt"), (2, "Alyssa"), (3, "Joint"), (4, "Outside")
            ):
                session.add(Transaction(
                    account_id=account_id,
                    transaction_date=date(2026, 9, account_id),
                    description=description,
                    amount=Decimal(str(account_id)),
                ))
        result = fetch_transactions(
            TransactionQueryParams(
                user_id=None, group_id=group_id, selected_month=(2026, 9)
            ),
            self.sessions,
        )
        self.assertEqual(result.total_count, 3)
        self.assertEqual(
            {row.description for row in result.rows}, {"Matt", "Alyssa", "Joint"}
        )
        self.assertEqual(len({row.id for row in result.rows}), 3)
        self.assertEqual({row[0] for row in result.accounts}, {1, 2, 3})

    def test_group_dashboard_aggregates_transactions_but_uses_group_goals(self):
        group_id = self._group_with_accounts()
        with self.sessions.begin() as session:
            salary = Category(name="Salary", color="#00ff00")
            food = Category(name="Food", color="#ff0000")
            session.add_all((salary, food))
            session.flush()
            session.add_all((
                Transaction(
                    account_id=1, category_id=salary.id,
                    transaction_type=TransactionType.INCOME,
                    transaction_date=date(2026, 9, 1),
                    description="Pay", amount=Decimal("1000"),
                ),
                Transaction(
                    account_id=2, category_id=food.id,
                    transaction_type=TransactionType.EXPENSE,
                    transaction_date=date(2026, 9, 2),
                    description="Groceries", amount=Decimal("-100"),
                ),
                Transaction(
                    account_id=3, category_id=food.id,
                    transaction_type=TransactionType.EXPENSE,
                    transaction_date=date(2026, 9, 3),
                    description="Joint groceries", amount=Decimal("-50"),
                ),
            ))
        data = get_dashboard_data(
            None,
            "monthly",
            (2026, 9),
            self.sessions,
            group_id=group_id,
        )
        self.assertEqual(data.regular_income, Decimal("1000"))
        self.assertEqual(data.gross_expense_spending, Decimal("150"))
        self.assertEqual(data.total_spending, Decimal("150"))

    def test_profile_context_and_switcher_keep_group_typed(self):
        group_id = create_group(
            "Household", "#9148e8", ("matt", "alyssa"),
            session_factory=self.sessions,
        )
        profiles = get_profiles(self.sessions)
        group_profile = next(profile for profile in profiles if profile["type"] == "group")
        self.assertEqual(group_profile["subtitle"], "Group • 2 members")
        context = ProfileContext.from_key(group_profile["key"])
        self.assertEqual(context.profile_type, ProfileType.GROUP)
        self.assertIsNone(context.user_id)
        self.assertEqual(context.group_id, group_id)

        dialog = SwitchUserDialog(profiles, "user:matt")
        selected = QSignalSpy(dialog.profile_selected)
        group_row = next(row for row in dialog.user_rows if row.profile_type == "group")
        group_row.activated.emit(group_row.profile_key)
        self.assertEqual(selected.at(0)[0], f"group:{group_id}")
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_add_profile_dialog_creates_group_from_selected_users(self):
        dialog = AddUserDialog(session_factory=self.sessions)
        created = QSignalSpy(dialog.group_created)
        dialog.group_button.click()
        dialog.name_input.setText("Household")
        dialog.member_checkboxes["matt"].setChecked(True)
        dialog.member_checkboxes["alyssa"].setChecked(True)
        dialog.add_user_button.click()

        self.assertEqual(created.count(), 1)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        with self.sessions() as session:
            group = session.get(Group, created.at(0)[0])
            self.assertEqual(group.name, "Household")
            self.assertEqual({item.user_id for item in group.memberships}, {"matt", "alyssa"})


if __name__ == "__main__":
    unittest.main()
