import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from database.models import Account, CategoryRule, Transaction
from utils.constants import TransactionType


@dataclass(frozen=True)
class RuleAssignment:
    transaction_type: TransactionType
    category_id: int | None


_E_TRANSFER_PATTERN = re.compile(r"\be\s+(?:transfer|tr|tfr)\b")
_INTERNAL_TRANSFER_CONTEXT = re.compile(
    r"\b(?:transfer|tfr|chequing|checking)\b"
)
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
    text = unicodedata.normalize("NFKC", description).casefold()
    text = re.sub(r"['’]", "", text)
    text = re.sub(r"[^\w]+", " ", text)
    return " ".join(text.split())


def is_e_transfer_description(description: str) -> bool:
    return bool(_E_TRANSFER_PATTERN.search(normalize_description(description)))


def _matching_rules(
    normalized: str,
    rules: dict[str, RuleAssignment],
) -> list[tuple[str, RuleAssignment]]:
    padded = f" {normalized} "
    return sorted(
        (
            (key, assignment)
            for key, assignment in rules.items()
            if key == normalized or (len(key) >= 4 and f" {key} " in padded)
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )


def _without_operational_category(assignment: RuleAssignment) -> RuleAssignment:
    if assignment.transaction_type in (
        TransactionType.E_TRANSFER,
        TransactionType.TRANSFER,
        TransactionType.CREDIT_CARD_PAYMENT,
    ):
        return RuleAssignment(assignment.transaction_type, None)
    return assignment


def classify_description(
    description: str,
    rules: dict[str, RuleAssignment] | None = None,
) -> RuleAssignment:
    """Classify one description using specific rules before generic patterns."""
    normalized = normalize_description(description)
    matching = _matching_rules(normalized, rules or {})

    for priority_type in (
        TransactionType.CREDIT_CARD_PAYMENT,
        TransactionType.TRANSFER,
    ):
        for _, assignment in matching:
            if assignment.transaction_type == priority_type:
                return _without_operational_category(assignment)

    if any(pattern.search(normalized) for pattern in _CREDIT_CARD_PAYMENT_PATTERNS):
        return RuleAssignment(TransactionType.CREDIT_CARD_PAYMENT, None)

    e_transfer = bool(_E_TRANSFER_PATTERN.search(normalized))
    if (
        any(term in normalized for term in _INTERNAL_TRANSFER_TERMS)
        and (e_transfer or _INTERNAL_TRANSFER_CONTEXT.search(normalized))
    ):
        return RuleAssignment(TransactionType.TRANSFER, None)

    for _, assignment in matching:
        if assignment.transaction_type == TransactionType.E_TRANSFER:
            return RuleAssignment(TransactionType.E_TRANSFER, None)

    if e_transfer:
        return RuleAssignment(TransactionType.E_TRANSFER, None)

    if matching:
        return _without_operational_category(matching[0][1])
    return RuleAssignment(TransactionType.EXPENSE, None)


def category_rules_for_user(
    session: Session,
    user_id: str,
) -> dict[str, RuleAssignment]:
    return {
        key: RuleAssignment(transaction_type, category_id)
        for key, transaction_type, category_id in session.execute(
            select(
                CategoryRule.description_key,
                CategoryRule.transaction_type,
                CategoryRule.category_id,
            ).where(CategoryRule.user_id == user_id)
        )
    }


def save_category_rule(
    session: Session,
    user_id: str,
    description: str,
    transaction_type: TransactionType,
    category_id: int | None,
) -> None:
    key = normalize_description(description)
    if not key:
        return

    rule = session.scalar(
        select(CategoryRule).where(
            CategoryRule.user_id == user_id,
            CategoryRule.description_key == key,
        )
    )
    if rule is None:
        session.add(CategoryRule(
            user_id=user_id,
            description_key=key,
            description_example=description,
            transaction_type=transaction_type,
            category_id=category_id,
        ))
    else:
        rule.transaction_type = transaction_type
        rule.category_id = category_id
        rule.description_example = description


def categorize_matching_transactions(
    session: Session,
    user_id: str,
    description: str,
    transaction_type: TransactionType,
    category_id: int | None,
) -> None:
    key = normalize_description(description)
    if not key:
        return

    descriptions = session.scalars(
        select(Transaction.description)
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == user_id)
        .distinct()
    )
    matches = [value for value in descriptions if normalize_description(value) == key]
    account_ids = select(Account.id).where(Account.user_id == user_id)
    for start in range(0, len(matches), 500):
        statement = (
            update(Transaction)
            .where(
                Transaction.account_id.in_(account_ids),
                Transaction.description.in_(matches[start:start + 500]),
                Transaction.is_deleted.is_(False),
            )
            .values(
                transaction_type=transaction_type,
                category_id=category_id,
            )
            .execution_options(synchronize_session=False)
        )
        session.execute(statement)
