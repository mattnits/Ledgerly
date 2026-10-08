import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.services.investments import (
    create_investment_account,
    create_investment_snapshot,
    delete_investment_account,
    get_account_current_value,
    get_account_history,
    get_account_summaries,
    get_investment_accounts,
    get_monthly_contribution_comparison,
    get_monthly_contributions,
    get_portfolio_history,
    get_recent_snapshots,
    get_total_portfolio_value,
    normalize_account_number_last7,
    set_investment_account_active,
    update_investment_account,
)
from app.models.models import Group, GroupMembership, InvestmentAccount, User


class InvestmentServicesTest(unittest.TestCase):
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
                User(id="owner", name="Owner", color="#111111"),
                User(id="member", name="Member", color="#222222"),
                User(id="outside", name="Outside", color="#333333"),
            ))

    def tearDown(self):
        self.engine.dispose()

    def account(self, name="TFSA", owner="owner", **kwargs):
        return create_investment_account(
            "Wealthsimple",
            name,
            user_id=owner,
            session_factory=self.sessions,
            **kwargs,
        )

    def test_create_account_stores_only_last_seven_and_initial_snapshot(self):
        account_id = self.account(
            account_number="acct-12x-34y-56",
            account_type="Tax-Free Savings Account",
            initial_value=Decimal("24350.125"),
            initial_date=date(2026, 9, 18),
        )

        with self.sessions() as session:
            account = session.get(InvestmentAccount, account_id)
            self.assertEqual(account.account_number_last7, "2X34Y56")
            self.assertEqual(len(account.snapshots), 1)
            self.assertEqual(account.snapshots[0].total_value, Decimal("24350.13"))
        self.assertEqual(normalize_account_number_last7("ab-99"), "AB99")

    def test_later_snapshot_is_current_and_totals_only_latest_values(self):
        first = self.account(initial_value="100.00", initial_date=date(2026, 1, 1))
        second = self.account(name="RRSP")
        third = self.account(name="FHSA", initial_value="400.00")
        create_investment_snapshot(
            first, date(2026, 2, 1), Decimal("150.00"), session_factory=self.sessions
        )
        create_investment_snapshot(
            second, date(2026, 2, 2), Decimal("250.00"), session_factory=self.sessions
        )

        self.assertEqual(
            get_account_current_value(first, session_factory=self.sessions),
            Decimal("150.00"),
        )
        self.assertEqual(
            get_total_portfolio_value(
                user_id="owner", session_factory=self.sessions
            ),
            Decimal("800.00"),
        )
        empty = self.account(name="No snapshots")
        self.assertEqual(
            get_account_current_value(empty, session_factory=self.sessions),
            Decimal("0.00"),
        )

    def test_edit_account_updates_alphanumeric_account_number(self):
        account_id = self.account(account_number="OLD1234")

        update_investment_account(
            account_id,
            institution="Wealthsimple",
            account_name="TFSA",
            account_number="new-acct-9z8y7x6",
            account_type="Tax-Free Savings Account",
            session_factory=self.sessions,
        )

        with self.sessions() as session:
            account = session.get(InvestmentAccount, account_id)
            self.assertEqual(account.account_number_last7, "9Z8Y7X6")

    def test_monthly_contributions_and_previous_month_comparison(self):
        account_id = self.account()
        create_investment_snapshot(
            account_id,
            date(2026, 8, 31),
            "1000",
            "100.10",
            session_factory=self.sessions,
        )
        create_investment_snapshot(
            account_id,
            date(2026, 9, 15),
            "1300",
            "200.20",
            session_factory=self.sessions,
        )
        create_investment_snapshot(
            account_id,
            date(2026, 9, 30),
            "1400",
            None,
            session_factory=self.sessions,
        )

        self.assertEqual(
            get_monthly_contributions(
                2026, 9, user_id="owner", session_factory=self.sessions
            ),
            Decimal("200.20"),
        )
        comparison = get_monthly_contribution_comparison(
            2026, 9, user_id="owner", session_factory=self.sessions
        )
        self.assertEqual(comparison.current, Decimal("200.20"))
        self.assertEqual(comparison.previous, Decimal("100.10"))

    def test_portfolio_history_carries_forward_each_accounts_latest_value(self):
        first = self.account(initial_value="100", initial_date=date(2026, 1, 1))
        second = self.account(name="RRSP")
        create_investment_snapshot(
            second, date(2026, 2, 1), "200", session_factory=self.sessions
        )
        create_investment_snapshot(
            first, date(2026, 3, 1), "150", session_factory=self.sessions
        )

        history = get_portfolio_history(
            user_id="owner", session_factory=self.sessions
        )
        self.assertEqual(
            [(point.snapshot_datetime.date(), point.total_value) for point in history],
            [
                (date(2026, 1, 1), Decimal("100.00")),
                (date(2026, 2, 1), Decimal("300.00")),
                (date(2026, 3, 1), Decimal("350.00")),
            ],
        )

    def test_recent_snapshots_are_newest_first_and_user_filtered(self):
        owner_account = self.account()
        outside_account = self.account(name="Outside", owner="outside")
        create_investment_snapshot(
            owner_account, date(2026, 9, 1), "100", session_factory=self.sessions
        )
        create_investment_snapshot(
            owner_account, date(2026, 9, 2), "200", session_factory=self.sessions
        )
        create_investment_snapshot(
            outside_account, date(2026, 9, 3), "999", session_factory=self.sessions
        )

        recent = get_recent_snapshots(
            user_id="owner", limit=5, session_factory=self.sessions
        )
        self.assertEqual([entry.total_value for entry in recent], [Decimal("200.00"), Decimal("100.00")])
        self.assertEqual(len(get_investment_accounts(
            user_id="owner", session_factory=self.sessions
        )), 1)

    def test_group_scope_includes_member_and_group_accounts_not_outsiders(self):
        with self.sessions.begin() as session:
            group = Group(name="Household")
            session.add(group)
            session.flush()
            session.add_all((
                GroupMembership(user_id="owner", group_id=group.id),
                GroupMembership(user_id="member", group_id=group.id),
            ))
            group_id = group.id

        owner_account = self.account(initial_value="100")
        member_account = self.account(name="RRSP", owner="member", initial_value="200")
        self.account(name="Outside", owner="outside", initial_value="999")
        group_account = create_investment_account(
            "Questrade",
            "Joint",
            group_id=group_id,
            initial_value="300",
            session_factory=self.sessions,
        )

        summaries = get_account_summaries(
            group_id=group_id, session_factory=self.sessions
        )
        self.assertEqual({item.id for item in summaries}, {
            owner_account, member_account, group_account,
        })
        self.assertEqual(
            get_total_portfolio_value(
                group_id=group_id, session_factory=self.sessions
            ),
            Decimal("600.00"),
        )

    def test_archiving_excludes_current_totals_but_preserves_history(self):
        account_id = self.account(initial_value="500")
        set_investment_account_active(
            account_id, False, session_factory=self.sessions
        )

        self.assertEqual(
            get_total_portfolio_value(
                user_id="owner", session_factory=self.sessions
            ),
            Decimal("0.00"),
        )
        self.assertEqual(len(get_account_history(
            account_id, session_factory=self.sessions
        )), 1)
        self.assertEqual(len(get_investment_accounts(
            user_id="owner", include_inactive=True, session_factory=self.sessions
        )), 1)

    def test_deleting_account_also_deletes_its_snapshot_history(self):
        account_id = self.account(initial_value="500")
        create_investment_snapshot(
            account_id, date(2026, 2, 1), "550", session_factory=self.sessions
        )
        self.assertEqual(len(get_account_history(
            account_id, session_factory=self.sessions
        )), 2)

        delete_investment_account(account_id, session_factory=self.sessions)

        with self.sessions() as session:
            self.assertIsNone(session.get(InvestmentAccount, account_id))
        self.assertEqual(get_account_history(
            account_id, session_factory=self.sessions
        ), ())


if __name__ == "__main__":
    unittest.main()
