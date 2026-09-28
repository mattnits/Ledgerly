import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.category_rules import RuleAssignment, classify_description
from database.dashboard import get_dashboard_data
from database.db import Base
from database.finance_services import monthly_financial_summary
from database.models import Account, Category, Transaction, User
from utils.constants import TransactionType


class ETransferClassificationTest(unittest.TestCase):
    def test_common_variations_and_priority(self):
        for description in (
            "E-TRANSFER", "E TRANSFER", "E-TR", "E TR", "E-TFR", "E TFR",
            "SEND E-TFR JANE DOE", "REV E-TFR JOHN DOE",
        ):
            with self.subTest(description=description):
                assignment = classify_description(description)
                self.assertEqual(assignment.transaction_type, TransactionType.E_TRANSFER)
                self.assertIsNone(assignment.category_id)

        self.assertEqual(
            classify_description("SEND E-TFR TO WEALTHSIMPLE").transaction_type,
            TransactionType.TRANSFER,
        )
        self.assertEqual(
            classify_description("E-TRANSFER TO TFSA").transaction_type,
            TransactionType.TRANSFER,
        )
        self.assertEqual(
            classify_description("CHEQUING -> WEALTHSIMPLE").transaction_type,
            TransactionType.TRANSFER,
        )
        self.assertEqual(
            classify_description("AMEX PAYMENT E-TRANSFER").transaction_type,
            TransactionType.CREDIT_CARD_PAYMENT,
        )

        rules = {
            "joint account": RuleAssignment(TransactionType.TRANSFER, 123),
            "e transfer": RuleAssignment(TransactionType.E_TRANSFER, 456),
        }
        assignment = classify_description("SEND E-TRANSFER JOINT ACCOUNT", rules)
        self.assertEqual(assignment.transaction_type, TransactionType.TRANSFER)
        self.assertIsNone(assignment.category_id)


class ETransferSummaryTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions.begin() as session:
            user = User(id="test-user", name="Test", color="#123456")
            salary = Category(name="Salary", color="#10b981")
            other_income = Category(name="Other Income", color="#34d399")
            food = Category(name="Food", color="#f97316")
            session.add_all((user, salary, other_income, food))
            session.flush()
            account = Account(
                user_id=user.id,
                name="Checking",
                institution="Test",
                account_type="debit",
            )
            session.add(account)
            session.flush()
            self.account_id = account.id
            self.category_ids = {
                "Salary": salary.id,
                "Other Income": other_income.id,
                "Food": food.id,
            }

    def tearDown(self):
        self.engine.dispose()

    def _add(self, month, amount, transaction_type, category=None):
        with self.sessions.begin() as session:
            session.add(Transaction(
                account_id=self.account_id,
                transaction_date=date(2026, month, 15),
                description=f"{transaction_type.value} {amount}",
                amount=Decimal(amount),
                transaction_type=transaction_type,
                category_id=self.category_ids.get(category),
            ))

    def test_positive_negative_and_balanced_months(self):
        self._add(9, "300", TransactionType.E_TRANSFER)
        self._add(9, "-100", TransactionType.E_TRANSFER)
        self._add(9, "1000", TransactionType.INCOME, "Salary")
        self._add(9, "50", TransactionType.INCOME, "Other Income")
        self._add(9, "-40", TransactionType.EXPENSE, "Food")
        self._add(9, "500", TransactionType.TRANSFER)
        self._add(9, "-200", TransactionType.CREDIT_CARD_PAYMENT)

        positive = monthly_financial_summary(
            2026, 9, user_id="test-user", session_factory=self.sessions
        )
        self.assertEqual(positive.e_transfer_received, Decimal("300"))
        self.assertEqual(positive.e_transfer_sent, Decimal("100"))
        self.assertEqual(positive.e_transfer_net, Decimal("200"))
        self.assertEqual(positive.regular_income, Decimal("1000"))
        self.assertEqual(positive.other_income, Decimal("50"))
        self.assertEqual(positive.total_income, Decimal("1250"))
        self.assertEqual(positive.gross_expense_spending, Decimal("40"))
        self.assertEqual(positive.e_transfer_spending_adjustment, Decimal("0"))
        self.assertEqual(positive.total_spending, Decimal("40"))

        dashboard = get_dashboard_data(
            "test-user", "monthly", (2026, 9), self.sessions
        )
        self.assertEqual(dashboard.total_income, Decimal("1250"))
        self.assertEqual(dashboard.total_spending, Decimal("40"))
        self.assertNotIn(
            "E-Transfer",
            {item.name for item in dashboard.category_spending},
        )

        self._add(10, "100", TransactionType.E_TRANSFER)
        self._add(10, "-400", TransactionType.E_TRANSFER)
        negative = monthly_financial_summary(
            2026, 10, user_id="test-user", session_factory=self.sessions
        )
        self.assertEqual(negative.e_transfer_net, Decimal("-300"))
        self.assertEqual(negative.total_income, Decimal("0"))
        self.assertEqual(negative.e_transfer_spending_adjustment, Decimal("300"))
        self.assertEqual(negative.total_spending, Decimal("300"))

        self._add(11, "200", TransactionType.E_TRANSFER)
        self._add(11, "-200", TransactionType.E_TRANSFER)
        balanced = monthly_financial_summary(
            2026, 11, user_id="test-user", session_factory=self.sessions
        )
        self.assertEqual(balanced.e_transfer_net, Decimal("0"))
        self.assertEqual(balanced.total_income, Decimal("0"))
        self.assertEqual(balanced.total_spending, Decimal("0"))

        all_time = get_dashboard_data("test-user", "all", (2026, 11), self.sessions)
        self.assertEqual(all_time.e_transfer_net, Decimal("-100"))
        self.assertEqual(all_time.e_transfer_income_adjustment, Decimal("200"))
        self.assertEqual(all_time.e_transfer_spending_adjustment, Decimal("300"))
        self.assertEqual(all_time.total_income, Decimal("1250"))
        self.assertEqual(all_time.total_spending, Decimal("340"))

if __name__ == "__main__":
    unittest.main()
