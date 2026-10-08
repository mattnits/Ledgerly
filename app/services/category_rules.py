import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.models import Account, Category, CategoryRule, Transaction
from app.utils.constants import (
    CATEGORY_FREE_TRANSACTION_TYPES,
    CATEGORY_OPTIONAL_TRANSACTION_TYPES,
    ClassificationSource,
    MatchType,
    TransactionType,
)


@dataclass(frozen=True)
class RuleAssignment:
    transaction_type: TransactionType | None
    category_id: int | None
    classification_source: str = ClassificationSource.DEFAULT.value
    matched_rule_id: int | None = None


@dataclass(frozen=True)
class RuleSpec:
    id: int | None
    description_key: str
    match_type: MatchType
    transaction_type: TransactionType | None
    category_id: int | None
    priority: int = 0
    account_id: int | None = None


@dataclass(frozen=True)
class RuleSummary:
    id: int
    pattern: str
    match_type: MatchType
    transaction_type: TransactionType | None
    category_id: int | None
    category_name: str | None
    priority: int
    is_active: bool
    account_id: int | None = None
    account_name: str | None = None


@dataclass(frozen=True)
class RulePrefill:
    pattern: str
    transaction_type: TransactionType | None
    category_id: int | None
    match_type: MatchType = MatchType.CONTAINS


_E_TRANSFER_PATTERN = re.compile(r"\be\s+(?:transfer|tr|tfr)\b")
_INTERNAL_TRANSFER_CONTEXT = re.compile(r"\b(?:transfer|tfr|chequing|checking)\b")
_CREDIT_CARD_PAYMENT_PATTERNS = (
    re.compile(r"\b(?:amex|visa|mastercard|credit card)\s+payment\b"),
    re.compile(r"\bpayment\s+(?:to\s+)?(?:amex|visa|mastercard|credit card)\b"),
)
_INTERNAL_TRANSFER_TERMS = (
    "wealthsimple",
    "tfsa",
    "rrsp",
    "savings account",
    "saving account",
    "brokerage",
)


def normalize_description(description: str) -> str:
    """Return a deterministic matching form without changing the stored text."""
    text = unicodedata.normalize("NFKC", description).casefold()
    text = re.sub(r"['\u2019]", "", text)
    text = re.sub(r"[^\w]+", " ", text)
    return " ".join(text.split())


def rule_prefill_from_transaction(transaction: Transaction) -> RulePrefill:
    return RulePrefill(
        pattern=normalize_description(transaction.description),
        transaction_type=transaction.transaction_type,
        category_id=transaction.category_id,
    )


def is_e_transfer_description(description: str) -> bool:
    return bool(_E_TRANSFER_PATTERN.search(normalize_description(description)))


def transaction_type_requires_category(
    transaction_type: TransactionType | None,
) -> bool:
    return (
        transaction_type is not None
        and transaction_type not in CATEGORY_OPTIONAL_TRANSACTION_TYPES
    )


def transaction_needs_review(transaction: Transaction) -> bool:
    return transaction.transaction_type is None or (
        transaction_type_requires_category(transaction.transaction_type)
        and transaction.category_id is None
    )


def needs_review_expression():
    required_values = [
        item.value
        for item in TransactionType
        if item not in CATEGORY_OPTIONAL_TRANSACTION_TYPES
    ]
    return or_(
        Transaction.transaction_type.is_(None),
        and_(
            Transaction.transaction_type.in_(required_values),
            Transaction.category_id.is_(None),
        ),
    )


def _rule_matches(normalized: str, rule: RuleSpec) -> bool:
    rule_key = normalize_description(rule.description_key)
    if not rule_key:
        return False
    if rule.match_type == MatchType.EXACT:
        return normalized == rule_key
    if rule.match_type == MatchType.STARTS_WITH:
        return normalized.startswith(rule_key)
    return rule_key in normalized


def _coerce_rules(
    rules: Iterable[RuleSpec] | dict[str, RuleAssignment] | None,
) -> list[RuleSpec]:
    if not rules:
        return []
    if isinstance(rules, dict):
        return [
            RuleSpec(
                id=None,
                description_key=key,
                match_type=MatchType.CONTAINS,
                transaction_type=assignment.transaction_type,
                category_id=assignment.category_id,
            )
            for key, assignment in rules.items()
        ]
    return list(rules)


def matching_rule(
    description: str,
    rules: Iterable[RuleSpec] | dict[str, RuleAssignment] | None,
    account_id: int | None = None,
) -> RuleSpec | None:
    normalized = normalize_description(description)
    matches = [
        rule
        for rule in _coerce_rules(rules)
        if (rule.account_id is None or rule.account_id == account_id)
        and _rule_matches(normalized, rule)
    ]
    if not matches:
        return None
    return max(
        matches,
        key=lambda rule: (
            rule.priority,
            rule.account_id is not None,
            rule.match_type == MatchType.EXACT,
            rule.match_type == MatchType.STARTS_WITH,
            len(normalize_description(rule.description_key)),
            -(rule.id or 0),
        ),
    )


def _without_operational_category(assignment: RuleAssignment) -> RuleAssignment:
    if assignment.transaction_type in CATEGORY_FREE_TRANSACTION_TYPES:
        return RuleAssignment(
            assignment.transaction_type,
            None,
            assignment.classification_source,
            assignment.matched_rule_id,
        )
    return assignment


def _default_classification(description: str) -> RuleAssignment:
    """Preserve the app's existing non-ML fallback classification behavior."""
    normalized = normalize_description(description)
    if any(pattern.search(normalized) for pattern in _CREDIT_CARD_PAYMENT_PATTERNS):
        return RuleAssignment(TransactionType.CREDIT_CARD_PAYMENT, None)

    e_transfer = bool(_E_TRANSFER_PATTERN.search(normalized))
    if (
        any(term in normalized for term in _INTERNAL_TRANSFER_TERMS)
        and (e_transfer or _INTERNAL_TRANSFER_CONTEXT.search(normalized))
    ):
        return RuleAssignment(TransactionType.TRANSFER, None)
    if e_transfer:
        return RuleAssignment(TransactionType.E_TRANSFER, None)
    return RuleAssignment(TransactionType.EXPENSE, None)


def classify_description(
    description: str,
    rules: Iterable[RuleSpec] | dict[str, RuleAssignment] | None = None,
    account_id: int | None = None,
) -> RuleAssignment:
    """Apply the highest-priority active rule, then existing local fallbacks."""
    rule = matching_rule(description, rules, account_id)
    fallback = _default_classification(description)
    if rule is None:
        return fallback

    assignment = RuleAssignment(
        rule.transaction_type or fallback.transaction_type,
        rule.category_id,
        ClassificationSource.RULE.value,
        rule.id,
    )
    return _without_operational_category(assignment)


def category_rules_for_user(session: Session, user_id: str) -> list[RuleSpec]:
    rows = session.execute(
        select(
            CategoryRule.id,
            CategoryRule.description_key,
            CategoryRule.match_type,
            CategoryRule.transaction_type,
            CategoryRule.category_id,
            CategoryRule.priority,
            CategoryRule.account_id,
        )
        .where(
            CategoryRule.user_id == user_id,
            CategoryRule.is_active.is_(True),
        )
        .order_by(CategoryRule.priority.desc(), CategoryRule.id)
    )
    return [RuleSpec(*row) for row in rows]


def list_category_rules(session: Session, user_id: str) -> list[RuleSummary]:
    rows = session.execute(
        select(
            CategoryRule.id,
            CategoryRule.description_example,
            CategoryRule.match_type,
            CategoryRule.transaction_type,
            CategoryRule.category_id,
            Category.name,
            CategoryRule.priority,
            CategoryRule.is_active,
            CategoryRule.account_id,
            Account.name,
        )
        .outerjoin(Category, CategoryRule.category_id == Category.id)
        .outerjoin(Account, CategoryRule.account_id == Account.id)
        .where(CategoryRule.user_id == user_id)
        .order_by(CategoryRule.priority.desc(), CategoryRule.id)
    )
    return [RuleSummary(*row) for row in rows]


def save_category_rule(
    session: Session,
    user_id: str,
    pattern: str,
    transaction_type: TransactionType | None,
    category_id: int | None,
    *,
    account_id: int | None = None,
    match_type: MatchType = MatchType.EXACT,
    priority: int = 0,
    is_active: bool = True,
    rule_id: int | None = None,
) -> CategoryRule:
    key = normalize_description(pattern)
    if not key:
        raise ValueError("Keyword / pattern is required")

    match_type = MatchType(match_type)
    if transaction_type in CATEGORY_FREE_TRANSACTION_TYPES:
        category_id = None
    if account_id is not None:
        valid_account = session.scalar(
            select(Account.id).where(
                Account.id == account_id,
                Account.user_id == user_id,
            )
        )
        if valid_account is None:
            raise ValueError("Account is no longer available")

    if rule_id is not None:
        rule = session.get(CategoryRule, rule_id)
        if rule is None or rule.user_id != user_id:
            raise ValueError("Classification rule is no longer available")
    else:
        rule = session.scalar(select(CategoryRule).where(
            CategoryRule.user_id == user_id,
            CategoryRule.description_key == key,
            CategoryRule.account_id == account_id,
        ))
    if rule is None:
        rule = CategoryRule(user_id=user_id, description_key=key, description_example=pattern)
        session.add(rule)

    rule.description_key = key
    rule.description_example = pattern.strip()
    rule.account_id = account_id
    rule.match_type = match_type
    rule.transaction_type = transaction_type
    rule.category_id = category_id
    rule.priority = int(priority)
    rule.is_active = bool(is_active)
    session.flush()
    return rule


def delete_category_rule(session: Session, user_id: str, rule_id: int) -> None:
    rule = session.get(CategoryRule, rule_id)
    if rule is None or rule.user_id != user_id:
        raise ValueError("Classification rule is no longer available")
    session.delete(rule)


def apply_rule_to_transaction(
    transaction: Transaction,
    rule: RuleSpec | CategoryRule,
    *,
    overwrite_manual: bool = False,
) -> bool:
    if (
        transaction.classification_source == ClassificationSource.MANUAL.value
        and not overwrite_manual
    ):
        return False
    spec = RuleSpec(
        rule.id,
        rule.description_key,
        MatchType(rule.match_type),
        rule.transaction_type,
        rule.category_id,
        rule.priority,
        rule.account_id,
    )
    if spec.account_id is not None and transaction.account_id != spec.account_id:
        return False
    if not _rule_matches(normalize_description(transaction.description), spec):
        return False

    if rule.transaction_type is not None:
        transaction.transaction_type = rule.transaction_type
    transaction.category_id = (
        None
        if transaction.transaction_type in CATEGORY_FREE_TRANSACTION_TYPES
        else rule.category_id
    )
    transaction.classification_source = ClassificationSource.RULE.value
    return True


def apply_rule_to_existing_transactions(
    session: Session,
    user_id: str,
    rule: CategoryRule,
    *,
    overwrite_manual: bool = False,
) -> int:
    if not rule.is_active:
        return 0
    active_rules = category_rules_for_user(session, user_id)
    selected_rule = RuleSpec(
        rule.id,
        rule.description_key,
        MatchType(rule.match_type),
        rule.transaction_type,
        rule.category_id,
        rule.priority,
        rule.account_id,
    )
    transactions = session.scalars(
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            Transaction.is_deleted.is_(False),
        )
    )
    updated = 0
    for transaction in transactions:
        if (
            selected_rule.account_id is not None
            and transaction.account_id != selected_rule.account_id
        ):
            continue
        normalized = normalize_description(transaction.description)
        if not _rule_matches(normalized, selected_rule):
            continue
        winner = matching_rule(
            transaction.description,
            active_rules,
            transaction.account_id,
        )
        if winner is not None:
            updated += apply_rule_to_transaction(
                transaction,
                winner,
                overwrite_manual=overwrite_manual,
            )
    return updated


def count_transactions_matching_rule(
    session: Session,
    user_id: str,
    pattern: str,
    match_type: MatchType,
    account_id: int | None = None,
) -> int:
    """Count active, non-manual transactions matching a prospective rule."""
    spec = RuleSpec(
        id=None,
        description_key=pattern,
        match_type=MatchType(match_type),
        transaction_type=None,
        category_id=None,
        account_id=account_id,
    )
    if not normalize_description(pattern):
        return 0

    statement = (
        select(Transaction.description, Transaction.classification_source)
        .join(Account, Transaction.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            Transaction.is_deleted.is_(False),
        )
    )
    if account_id is not None:
        statement = statement.where(Account.id == account_id)
    rows = session.execute(statement)
    return sum(
        source != ClassificationSource.MANUAL.value
        and _rule_matches(normalize_description(description), spec)
        for description, source in rows
    )
