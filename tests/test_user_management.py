import os
import unittest
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base, get_profiles
from app.services.groups import create_group
from app.models.models import (
    Account,
    Category,
    Group,
    GroupMembership,
    Import,
    InvestmentAccount,
    InvestmentSnapshot,
    MonthlyCategoryBudget,
    SavingsGoal,
    SavingsSnapshot,
    Transaction,
    User,
)
from app.core.session_context import CurrentSession
from app.services.user_management import (
    AuthorizationError,
    GroupHasOwnedDataError,
    LastAdminError,
    create_user,
    delete_group,
    delete_user,
    leave_group,
    management_snapshot,
    set_admin,
)
from app.ui.dialogs.switch_user import SwitchUserDialog
from app.ui.shell import ShellWindow
from app.ui.pages.user_management import UserManagementPage


class UserManagementServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)

    def tearDown(self):
        self.engine.dispose()

    def _users(self):
        first = create_user("Matt", "#3397f5", session_factory=self.sessions)
        second = create_user("Alyssa", "#ef4a8b", session_factory=self.sessions)
        return first, second

    def test_first_user_is_admin_and_second_user_is_not(self):
        first, second = self._users()
        with self.sessions() as session:
            self.assertTrue(session.get(User, first).is_admin)
            self.assertFalse(session.get(User, second).is_admin)

    def test_admin_can_promote_and_demote_while_last_admin_is_protected(self):
        first, second = self._users()
        set_admin(first, second, True, session_factory=self.sessions)
        set_admin(first, second, False, session_factory=self.sessions)
        with self.assertRaises(LastAdminError):
            set_admin(first, first, False, session_factory=self.sessions)
        with self.sessions() as session:
            self.assertTrue(session.get(User, first).is_admin)

    def test_normal_user_cannot_perform_admin_actions(self):
        first, second = self._users()
        with self.assertRaises(AuthorizationError):
            set_admin(second, second, True, session_factory=self.sessions)
        with self.assertRaises(AuthorizationError):
            delete_user(second, first, session_factory=self.sessions)

    def test_last_admin_cannot_delete_self_and_admin_list_delete_rejects_self(self):
        first, _second = self._users()
        with self.assertRaises(AuthorizationError):
            delete_user(first, first, session_factory=self.sessions)
        with self.assertRaises(LastAdminError):
            delete_user(
                first, first, allow_self=True, session_factory=self.sessions
            )

    def test_leave_group_removes_only_membership_and_preserves_owned_data(self):
        first, second = self._users()
        group_id = create_group(
            "Household", "#57c978", (first, second), session_factory=self.sessions
        )
        with self.sessions.begin() as session:
            account = Account(
                user_id=second, name="Chequing", institution="Bank",
                account_type="Chequing",
            )
            session.add(account)
            session.flush()
            session.add(Transaction(
                account_id=account.id, transaction_date=date(2026, 1, 1),
                description="Kept", amount=Decimal("12.00"),
            ))
        leave_group(second, group_id, session_factory=self.sessions)
        with self.sessions() as session:
            self.assertIsNone(session.scalar(select(GroupMembership).where(
                GroupMembership.user_id == second,
                GroupMembership.group_id == group_id,
            )))
            self.assertIsNotNone(session.scalar(select(Account).where(
                Account.user_id == second
            )))
            self.assertIsNotNone(session.get(User, second))

    def test_admin_deletes_group_links_without_deleting_member_data(self):
        admin, second = self._users()
        group_id = create_group(
            "Household", "#57c978", (admin, second), session_factory=self.sessions
        )
        with self.sessions.begin() as session:
            account = Account(
                user_id=second,
                name="Personal",
                institution="Bank",
                account_type="Chequing",
            )
            session.add(account)
            session.flush()
            account_id = account.id

        delete_group(admin, group_id, session_factory=self.sessions)

        with self.sessions() as session:
            self.assertIsNone(session.get(Group, group_id))
            self.assertFalse(session.scalars(select(GroupMembership).where(
                GroupMembership.group_id == group_id
            )).all())
            self.assertIsNotNone(session.get(Account, account_id))
            self.assertIsNotNone(session.get(User, second))

    def test_group_delete_requires_admin_and_blocks_direct_group_data(self):
        admin, normal = self._users()
        group_id = create_group(
            "Household", "#57c978", (admin, normal), session_factory=self.sessions
        )
        with self.assertRaises(AuthorizationError):
            delete_group(normal, group_id, session_factory=self.sessions)
        with self.sessions.begin() as session:
            account = Account(
                group_id=group_id,
                name="Joint",
                institution="Bank",
                account_type="Chequing",
            )
            session.add(account)
            session.flush()
            account_id = account.id
        with self.assertRaises(GroupHasOwnedDataError):
            delete_group(admin, group_id, session_factory=self.sessions)
        with self.sessions() as session:
            self.assertIsNotNone(session.get(Group, group_id))
            self.assertIsNotNone(session.get(Account, account_id))

    def test_normal_snapshot_includes_tables_and_only_own_memberships(self):
        first, second = self._users()
        group_id = create_group(
            "Household", "#57c978", (second,), session_factory=self.sessions
        )
        snapshot = management_snapshot(second, session_factory=self.sessions)
        self.assertFalse(snapshot["current_user"]["is_admin"])
        self.assertEqual([item["id"] for item in snapshot["memberships"]], [group_id])
        self.assertEqual(len(snapshot["users"]), 2)
        self.assertEqual(len(snapshot["groups"]), 1)
        admin_snapshot = management_snapshot(first, session_factory=self.sessions)
        self.assertEqual(len(admin_snapshot["users"]), 2)
        self.assertEqual(len(admin_snapshot["groups"]), 1)

    def test_deleting_other_user_removes_owned_data_not_other_or_group_data(self):
        admin, target = self._users()
        group_id = create_group(
            "Household", "#57c978", (admin, target), session_factory=self.sessions
        )
        with self.sessions.begin() as session:
            system = Category(
                name="Food", color="#ff0000", is_default=True, is_system=True
            )
            custom = Category(
                name="Target Custom", color="#00ff00", is_default=False,
                is_system=False, created_by_user_id=target,
            )
            session.add_all((system, custom))
            session.flush()
            target_account = Account(
                user_id=target, name="Target", institution="Bank",
                account_type="Chequing",
            )
            other_account = Account(
                user_id=admin, name="Admin", institution="Bank",
                account_type="Chequing",
            )
            group_account = Account(
                group_id=group_id, name="Joint", institution="Bank",
                account_type="Chequing",
            )
            session.add_all((target_account, other_account, group_account))
            session.flush()
            imported = Import(account_id=target_account.id, file_name="statement.csv")
            session.add(imported)
            session.flush()
            session.add_all((
                Transaction(
                    account_id=target_account.id, import_id=imported.id,
                    category_id=custom.id, transaction_date=date(2026, 1, 1),
                    description="Target", amount=Decimal("1"),
                ),
                Transaction(
                    account_id=other_account.id, category_id=system.id,
                    transaction_date=date(2026, 1, 2), description="Admin",
                    amount=Decimal("2"),
                ),
                Transaction(
                    account_id=group_account.id, category_id=system.id,
                    transaction_date=date(2026, 1, 3), description="Joint",
                    amount=Decimal("3"),
                ),
            ))
            investment = InvestmentAccount(
                user_id=target, institution="Broker", account_name="TFSA"
            )
            session.add(investment)
            session.flush()
            session.add(InvestmentSnapshot(
                investment_account_id=investment.id,
                snapshot_datetime=datetime(2026, 1, 1),
                total_value=Decimal("100"),
            ))
            session.add_all((
                SavingsGoal(user_id=target, year=2026, month=1,
                            target_amount=Decimal("50")),
                SavingsSnapshot(
                    user_id=target, snapshot_date=date(2026, 1, 1),
                    amount_saved_this_month=Decimal("5"),
                ),
                MonthlyCategoryBudget(
                    user_id=target, category_id=system.id, year=2026, month=1,
                    target_amount=Decimal("20"),
                ),
            ))
        delete_user(admin, target, session_factory=self.sessions)
        with self.sessions() as session:
            self.assertIsNone(session.get(User, target))
            self.assertFalse(session.scalars(select(Account).where(
                Account.user_id == target
            )).all())
            self.assertFalse(session.scalars(select(InvestmentAccount).where(
                InvestmentAccount.user_id == target
            )).all())
            self.assertFalse(session.scalars(select(SavingsGoal).where(
                SavingsGoal.user_id == target
            )).all())
            self.assertFalse(session.scalars(select(GroupMembership).where(
                GroupMembership.user_id == target
            )).all())
            self.assertIsNotNone(session.get(User, admin))
            self.assertIsNotNone(session.get(Group, group_id))
            self.assertEqual(session.scalar(select(Account).where(
                Account.user_id == admin
            )).name, "Admin")
            self.assertEqual(session.scalar(select(Account).where(
                Account.group_id == group_id
            )).name, "Joint")
            self.assertIsNotNone(session.scalar(select(Category).where(
                Category.is_system
            )))
            self.assertIsNone(session.scalar(select(Category).where(
                Category.name == "Target Custom"
            )))

    def test_referenced_custom_category_is_kept_orphan_safe(self):
        admin, target = self._users()
        with self.sessions.begin() as session:
            custom = Category(
                name="Shared Reference", color="#00ff00", is_default=False,
                is_system=False, created_by_user_id=target,
            )
            other = Account(
                user_id=admin, name="Admin", institution="Bank",
                account_type="Chequing",
            )
            session.add_all((custom, other))
            session.flush()
            session.add(Transaction(
                account_id=other.id, category_id=custom.id,
                transaction_date=date(2026, 1, 1), description="Reference",
                amount=Decimal("1"),
            ))
        delete_user(admin, target, session_factory=self.sessions)
        with self.sessions() as session:
            category = session.scalar(select(Category).where(
                Category.name == "Shared Reference"
            ))
            self.assertIsNotNone(category)
            self.assertIsNone(category.created_by_user_id)
            self.assertFalse(category.is_system)

    def test_delete_rolls_back_when_commit_fails(self):
        admin, target = self._users()
        with self.sessions.begin() as session:
            session.add(Account(
                user_id=target, name="Target", institution="Bank",
                account_type="Chequing",
            ))

        class FailingSession(Session):
            pass

        failing_factory = sessionmaker(bind=self.engine, class_=FailingSession)

        def fail_commit(_session):
            raise RuntimeError("simulated commit failure")

        event.listen(FailingSession, "before_commit", fail_commit)
        try:
            with self.assertRaises(RuntimeError):
                delete_user(admin, target, session_factory=failing_factory)
        finally:
            event.remove(FailingSession, "before_commit", fail_commit)
        with self.sessions() as session:
            self.assertIsNotNone(session.get(User, target))
            self.assertIsNotNone(session.scalar(select(Account).where(
                Account.user_id == target
            )))


class UserManagementUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_switcher_marks_admin_and_distinguishes_avatar_shapes(self):
        profiles = [
            {"key": "user:u1", "type": "user", "id": "u1", "name": "Matt",
             "color": "#3397f5", "subtitle": "Personal", "is_admin": True},
            {"key": "group:1", "type": "group", "id": 1, "name": "Household",
             "color": "#57c978", "subtitle": "Group • 2 members"},
        ]
        dialog = SwitchUserDialog(profiles, "group:1", can_manage_groups=False)
        people, group = dialog.user_rows
        self.assertEqual(people.name_label.fullText(), "Matt")
        self.assertFalse(people.admin_star.pixmap().isNull())
        self.assertEqual(people.profile_type, "user")
        self.assertEqual(group.profile_type, "group")
        self.assertEqual(people.avatar.property("profileType"), "user")
        self.assertEqual(group.avatar.property("profileType"), "group")
        self.assertTrue(group.property("selected"))
        self.assertFalse(hasattr(group, "edit_button"))
        dialog.close()

    def test_current_user_permissions_survive_group_profile_switch(self):
        context = CurrentSession(current_user_id="admin")
        context.set_active_profile("group:12")
        self.assertEqual(context.current_user_id, "admin")
        self.assertEqual(context.active_profile_key, "group:12")
        self.assertIsNone(context.active_profile.user_id)

    def test_page_disables_admin_controls_for_normal_users(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine, expire_on_commit=False)
        admin = create_user("Matt", "#3397f5", session_factory=sessions)
        normal = create_user("Alyssa", "#ef4a8b", session_factory=sessions)
        page = UserManagementPage(session_factory=sessions)
        page.set_current_user(normal)
        normal_text = " ".join(
            label.text() for label in page.findChildren(QLabel)
        )
        self.assertIn("All Users", normal_text)
        self.assertIn("Groups", normal_text)
        self.assertFalse(page.add_profile_button.isEnabled())
        self.assertFalse(page.users_card.isEnabled())
        self.assertFalse(page.groups_card.isEnabled())
        self.assertEqual(page.profile_name_label.fullText(), "Alyssa")
        page.set_current_user(admin)
        self.app.processEvents()
        admin_text = " ".join(
            label.text() for label in page.findChildren(QLabel)
        )
        self.assertIn("All Users", admin_text)
        self.assertTrue(page.add_profile_button.isEnabled())
        self.assertTrue(page.users_card.isEnabled())
        self.assertTrue(page.groups_card.isEnabled())
        self.assertEqual(page.profile_name_label.fullText(), "Matt")
        page.close()
        engine.dispose()

    def test_management_identity_follows_user_and_group_uses_first_admin(self):
        profiles = [
            {"key": "user:normal", "type": "user", "id": "normal",
             "is_admin": False},
            {"key": "user:admin-1", "type": "user", "id": "admin-1",
             "is_admin": True},
            {"key": "user:admin-2", "type": "user", "id": "admin-2",
             "is_admin": True},
            {"key": "group:7", "type": "group", "id": 7},
        ]

        self.assertEqual(
            ShellWindow._management_user_id(profiles, "user:normal"),
            "normal",
        )
        self.assertEqual(
            ShellWindow._management_user_id(profiles, "group:7"),
            "admin-1",
        )

    def test_management_page_reflows_and_uses_icon_only_row_actions(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine, expire_on_commit=False)
        admin = create_user("Matt", "#3397f5", session_factory=sessions)
        second = create_user("Alyssa", "#ef4a8b", session_factory=sessions)
        create_group(
            "Household", "#57c978", (admin, second), session_factory=sessions
        )
        page = UserManagementPage(session_factory=sessions)
        page.resize(1000, 760)
        page.set_current_user(admin)
        page.show()
        self.app.processEvents()
        self.assertFalse(page._top_is_stacked)
        action_buttons = [
            button for button in page.findChildren(QPushButton)
            if button.property("iconOnly")
        ]
        self.assertGreaterEqual(len(action_buttons), 5)
        self.assertTrue(all(not button.text() for button in action_buttons))
        self.assertTrue(all(
            row.layout().itemAtPosition(0, 4).widget().width()
            == page.USER_ACTION_WIDTH
            for row in page._user_rows
        ))

        page.resize(680, 760)
        self.app.processEvents()
        self.assertTrue(page._top_is_stacked)
        self.assertTrue(all(
            not widget.isVisible() for widget in page._user_created_widgets
        ))
        page.close()
        engine.dispose()

    def test_management_refresh_keeps_the_current_page_and_profile(self):
        shell = SimpleNamespace(
            session=CurrentSession(current_user_id="admin"),
            load_profiles=Mock(),
        )
        shell.session.set_active_profile("group:12")

        ShellWindow.refresh_profiles(shell)

        shell.load_profiles.assert_called_once_with(
            "group:12",
            navigate_to_dashboard=False,
        )


if __name__ == "__main__":
    unittest.main()
