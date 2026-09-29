import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.category_rules import (
    RuleSpec,
    apply_rule_to_existing_transactions,
    category_rules_for_user,
    classify_description,
    matching_rule,
    needs_review_expression,
    normalize_description,
    rule_prefill_from_transaction,
    save_category_rule,
    transaction_needs_review,
)
from database.db import Base
from database.models import Account, Category, CategoryRule, Transaction, User
from utils.constants import ClassificationSource, MatchType, TransactionType


class TransactionClassificationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.sessions = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        with self.sessions.begin() as session:
            user = User(id="test-user", name="Test", color="#123456")
            food = Category(name="Food", color="#f97316")
            salary = Category(name="Salary", color="#10b981")
            session.add_all((user, food, salary))
            session.flush()
            account = Account(
                user_id=user.id,
                name="Checking",
                institution="Test",
                account_type="debit",
            )
            second_account = Account(
                user_id=user.id,
                name="Credit Card",
                institution="Test",
                account_type="credit",
            )
            session.add_all((account, second_account))
            session.flush()
            self.account_id = account.id
            self.second_account_id = second_account.id
            self.food_id = food.id
            self.salary_id = salary.id

    def tearDown(self):
        self.engine.dispose()

    def _save_rule(
        self,
        pattern,
        transaction_type,
        category_id=None,
        *,
        priority=0,
        match_type=MatchType.CONTAINS,
        account_id=None,
    ):
        with self.sessions.begin() as session:
            save_category_rule(
                session,
                "test-user",
                pattern,
                transaction_type,
                category_id,
                priority=priority,
                match_type=match_type,
                account_id=account_id,
            )

    def _classify(self, description, account_id=None):
        with self.sessions() as session:
            rules = category_rules_for_user(session, "test-user")
            return classify_description(description, rules, account_id)

    def test_account_specific_rule_only_applies_to_its_account(self):
        self._save_rule(
            "COFFEE",
            TransactionType.EXPENSE,
            self.food_id,
            priority=10,
        )
        self._save_rule(
            "COFFEE",
            TransactionType.INCOME,
            self.salary_id,
            priority=10,
            account_id=self.account_id,
        )

        checking = self._classify("COFFEE SHOP", self.account_id)
        credit_card = self._classify("COFFEE SHOP", self.second_account_id)
        without_account = self._classify("COFFEE SHOP")
        self.assertEqual(checking.transaction_type, TransactionType.INCOME)
        self.assertEqual(checking.category_id, self.salary_id)
        self.assertEqual(credit_card.transaction_type, TransactionType.EXPENSE)
        self.assertEqual(credit_card.category_id, self.food_id)
        self.assertEqual(without_account.transaction_type, TransactionType.EXPENSE)

        with self.sessions.begin() as session:
            session.add_all((
                Transaction(
                    account_id=self.account_id,
                    transaction_date=date.today(),
                    description="COFFEE SHOP",
                    amount=Decimal("5.00"),
                    transaction_type=TransactionType.EXPENSE,
                ),
                Transaction(
                    account_id=self.second_account_id,
                    transaction_date=date.today(),
                    description="COFFEE SHOP",
                    amount=Decimal("-5.00"),
                    transaction_type=TransactionType.EXPENSE,
                ),
            ))
        with self.sessions.begin() as session:
            scoped_rule = session.scalar(select(CategoryRule).where(
                CategoryRule.account_id == self.account_id
            ))
            updated = apply_rule_to_existing_transactions(
                session, "test-user", scoped_rule
            )
            self.assertEqual(updated, 1)

        with self.sessions() as session:
            rows = session.scalars(
                select(Transaction).order_by(Transaction.account_id)
            ).all()
            by_account = {row.account_id: row for row in rows}
            self.assertEqual(
                by_account[self.account_id].transaction_type,
                TransactionType.INCOME,
            )
            self.assertEqual(
                by_account[self.second_account_id].transaction_type,
                TransactionType.EXPENSE,
            )

    def test_common_rules_assign_transaction_type_and_optional_category(self):
        self._save_rule("TIM HORTONS", TransactionType.EXPENSE, self.food_id)
        self._save_rule("PAYROLL", TransactionType.INCOME, self.salary_id)
        self._save_rule("E-TFR", TransactionType.E_TRANSFER)
        self._save_rule("AMEX PAYMENT", TransactionType.CREDIT_CARD_PAYMENT)

        cases = (
            ("TIM HORTONS #123", TransactionType.EXPENSE, self.food_id),
            ("EMPLOYER PAYROLL", TransactionType.INCOME, self.salary_id),
            ("SEND E-TFR JANE", TransactionType.E_TRANSFER, None),
            ("AMEX PAYMENT THANK YOU", TransactionType.CREDIT_CARD_PAYMENT, None),
        )
        for description, transaction_type, category_id in cases:
            with self.subTest(description=description):
                assignment = self._classify(description)
                self.assertEqual(assignment.transaction_type, transaction_type)
                self.assertEqual(assignment.category_id, category_id)
                self.assertEqual(
                    assignment.classification_source,
                    ClassificationSource.RULE.value,
                )

    def test_normalization_and_contains_matching_handle_separator_variants(self):
        variants = (
            "Tim-Hortons  Aurora",
            "TIM HORTONS AURORA",
            " tim.hortons   aurora ",
        )
        self.assertEqual(
            {normalize_description(description) for description in variants},
            {"tim hortons aurora"},
        )

        self._save_rule("TIM HORTONS", TransactionType.EXPENSE, self.food_id)
        for description in variants:
            with self.subTest(description=description):
                self.assertEqual(self._classify(description).category_id, self.food_id)

    def test_exact_matching_uses_the_whole_normalized_description(self):
        self._save_rule(
            "TIM HORTONS AURORA",
            TransactionType.EXPENSE,
            self.food_id,
            match_type=MatchType.EXACT,
        )
        self.assertEqual(
            self._classify("Tim-Hortons Aurora").category_id,
            self.food_id,
        )
        self.assertIsNone(self._classify("Tim-Hortons Aurora ON").category_id)

    def test_specific_match_type_wins_at_equal_priority(self):
        rules = (
            RuleSpec(
                1, "coffee shop", MatchType.CONTAINS,
                TransactionType.INCOME, self.salary_id, 10,
            ),
            RuleSpec(
                2, "coffee", MatchType.STARTS_WITH,
                TransactionType.EXPENSE, self.food_id, 10,
            ),
        )
        winner = matching_rule("COFFEE SHOP", rules)
        self.assertIsNotNone(winner)
        self.assertEqual(winner.id, 2)

        exact = RuleSpec(
            3, "coffee shop", MatchType.EXACT,
            TransactionType.INCOME, self.salary_id, 10,
        )
        winner = matching_rule("COFFEE SHOP", (*rules, exact))
        self.assertIsNotNone(winner)
        self.assertEqual(winner.id, 3)

    def test_rule_prefill_uses_normalized_text_and_current_assignment(self):
        transaction = Transaction(
            account_id=self.account_id,
            transaction_date=date.today(),
            description="  Tim-Hortons   Aurora ",
            amount=Decimal("-5.00"),
            transaction_type=TransactionType.EXPENSE,
            category_id=self.food_id,
        )
        prefill = rule_prefill_from_transaction(transaction)
        self.assertEqual(prefill.pattern, "tim hortons aurora")
        self.assertEqual(prefill.match_type, MatchType.CONTAINS)
        self.assertEqual(prefill.transaction_type, TransactionType.EXPENSE)
        self.assertEqual(prefill.category_id, self.food_id)

    def test_higher_priority_specific_rule_wins(self):
        self._save_rule("E-TFR", TransactionType.E_TRANSFER, priority=0)
        self._save_rule(
            "E-TFR TO WEALTHSIMPLE",
            TransactionType.TRANSFER,
            priority=100,
        )
        assignment = self._classify("SEND E-TFR TO WEALTHSIMPLE TFSA")
        self.assertEqual(assignment.transaction_type, TransactionType.TRANSFER)
        self.assertIsNone(assignment.category_id)

        with self.sessions.begin() as session:
            transaction = Transaction(
                account_id=self.account_id,
                transaction_date=date.today(),
                description="SEND E-TFR TO WEALTHSIMPLE TFSA",
                amount=Decimal("-25.00"),
                transaction_type=TransactionType.EXPENSE,
            )
            session.add(transaction)
        with self.sessions.begin() as session:
            broad_rule = session.scalar(select(CategoryRule).where(
                CategoryRule.priority == 0
            ))
            apply_rule_to_existing_transactions(
                session, "test-user", broad_rule
            )
        with self.sessions() as session:
            transaction = session.scalar(select(Transaction))
            self.assertEqual(
                transaction.transaction_type,
                TransactionType.TRANSFER,
            )

    def test_starts_with_and_exact_match_types(self):
        self._save_rule(
            "COFFEE",
            TransactionType.EXPENSE,
            self.food_id,
            match_type=MatchType.STARTS_WITH,
        )
        self._save_rule(
            "PAYROLL",
            TransactionType.INCOME,
            self.salary_id,
            match_type=MatchType.EXACT,
        )
        self.assertEqual(
            self._classify("COFFEE SHOP").category_id,
            self.food_id,
        )
        self.assertIsNone(self._classify("SHOP COFFEE").category_id)
        self.assertEqual(
            self._classify("PAYROLL").transaction_type,
            TransactionType.INCOME,
        )
        self.assertEqual(
            self._classify("PAYROLL EXTRA").transaction_type,
            TransactionType.EXPENSE,
        )

    def test_apply_to_existing_is_explicit_and_protects_manual_rows(self):
        with self.sessions.begin() as session:
            session.add_all((
                Transaction(
                    account_id=self.account_id,
                    transaction_date=date.today(),
                    description="TIM HORTONS ONE",
                    amount=Decimal("-5.00"),
                    transaction_type=TransactionType.EXPENSE,
                    classification_source=ClassificationSource.DEFAULT.value,
                ),
                Transaction(
                    account_id=self.account_id,
                    transaction_date=date.today(),
                    description="TIM HORTONS MANUAL",
                    amount=Decimal("-7.00"),
                    transaction_type=TransactionType.INCOME,
                    category_id=self.salary_id,
                    classification_source=ClassificationSource.MANUAL.value,
                ),
            ))

        with self.sessions.begin() as session:
            rule = save_category_rule(
                session,
                "test-user",
                "TIM HORTONS",
                TransactionType.EXPENSE,
                self.food_id,
                match_type=MatchType.CONTAINS,
            )

        with self.sessions() as session:
            rows = session.scalars(select(Transaction).order_by(Transaction.id)).all()
            self.assertIsNone(rows[0].category_id)
            self.assertEqual(rows[1].category_id, self.salary_id)

        with self.sessions.begin() as session:
            rule = session.merge(rule)
            updated = apply_rule_to_existing_transactions(
                session, "test-user", rule
            )
            self.assertEqual(updated, 1)

        with self.sessions() as session:
            rows = session.scalars(select(Transaction).order_by(Transaction.id)).all()
            self.assertEqual(
                [row.description for row in rows],
                ["TIM HORTONS ONE", "TIM HORTONS MANUAL"],
            )
            self.assertEqual(rows[0].category_id, self.food_id)
            self.assertEqual(
                rows[0].classification_source,
                ClassificationSource.RULE.value,
            )
            self.assertEqual(rows[1].transaction_type, TransactionType.INCOME)
            self.assertEqual(rows[1].category_id, self.salary_id)
            self.assertEqual(
                rows[1].classification_source,
                ClassificationSource.MANUAL.value,
            )

    def test_needs_review_respects_category_optional_transaction_types(self):
        expense = Transaction(
            account_id=self.account_id,
            transaction_date=date.today(),
            description="Expense",
            amount=Decimal("-1.00"),
            transaction_type=TransactionType.EXPENSE,
        )
        e_transfer = Transaction(
            account_id=self.account_id,
            transaction_date=date.today(),
            description="E-transfer",
            amount=Decimal("1.00"),
            transaction_type=TransactionType.E_TRANSFER,
        )
        unresolved = Transaction(
            account_id=self.account_id,
            transaction_date=date.today(),
            description="Unknown",
            amount=Decimal("0.00"),
            transaction_type=None,
        )
        self.assertTrue(transaction_needs_review(expense))
        self.assertFalse(transaction_needs_review(e_transfer))
        self.assertTrue(transaction_needs_review(unresolved))

        with self.sessions.begin() as session:
            session.add_all((expense, e_transfer, unresolved))
        with self.sessions() as session:
            review_descriptions = set(session.scalars(
                select(Transaction.description).where(needs_review_expression())
            ))
        self.assertEqual(review_descriptions, {"Expense", "Unknown"})


if __name__ == "__main__":
    unittest.main()
