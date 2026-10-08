from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
import hashlib
from typing import Any, Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from database.category_rules import normalize_description
from database.models import Account, Import, Transaction


class DuplicateDecision(StrEnum):
    UNRESOLVED = "unresolved"
    KEEP = "keep"
    SKIP = "skip"


@dataclass(frozen=True)
class IncomingTransaction:
    account_id: int
    account_name: str
    transaction_date: date
    description: str
    amount: Decimal
    source_file: str
    source_file_hash: str
    batch_file_id: str
    source_transaction_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def fingerprint(self) -> str:
        return build_transaction_fingerprint(
            self.account_id,
            self.transaction_date,
            self.description,
            self.amount,
        )


@dataclass(frozen=True)
class ExistingTransactionSnapshot:
    id: int
    account_id: int
    account_name: str
    transaction_date: date
    description: str
    amount: Decimal
    imported_at: datetime
    source_file: str | None
    source_file_hash: str | None
    source_transaction_id: str | None
    fingerprint: str
    is_manual: bool


@dataclass(frozen=True)
class DefiniteDuplicate:
    incoming: IncomingTransaction
    reason: str


@dataclass
class PossibleDuplicate:
    candidate_id: str
    incoming: IncomingTransaction
    existing_matches: tuple[ExistingTransactionSnapshot, ...]
    canonical_key: str
    reason: str
    decision: DuplicateDecision = DuplicateDecision.UNRESOLVED


@dataclass(frozen=True)
class DuplicateClassificationResult:
    new_rows: tuple[IncomingTransaction, ...]
    definite_duplicates: tuple[DefiniteDuplicate, ...]
    possible_duplicates: tuple[PossibleDuplicate, ...]


@dataclass(frozen=True)
class ExistingDuplicateCandidate:
    account_id: int
    account_name: str
    transaction_date: date
    description: str
    amount: Decimal
    count: int


@dataclass
class ExistingDuplicateState:
    rows: tuple[ExistingTransactionSnapshot, ...]
    by_source_id: dict[tuple[int, str], tuple[ExistingTransactionSnapshot, ...]]
    by_fingerprint: dict[str, tuple[ExistingTransactionSnapshot, ...]]
    by_file_hash_and_fingerprint: dict[
        tuple[int, str, str], tuple[ExistingTransactionSnapshot, ...]
    ]


def _money_text(amount: Decimal) -> str:
    return format(Decimal(amount).quantize(Decimal("0.01")), "f")


def build_canonical_transaction_key(
    account_id: int,
    transaction_date: date,
    description: str,
    amount: Decimal,
) -> str:
    """Return the stable, human-inspectable fallback transaction identity."""
    return "|".join((
        str(account_id),
        transaction_date.isoformat(),
        normalize_description(description),
        _money_text(amount),
    ))


def build_transaction_fingerprint(
    account_id: int,
    transaction_date: date,
    description: str,
    amount: Decimal,
) -> str:
    key = build_canonical_transaction_key(
        account_id, transaction_date, description, amount
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def load_existing_duplicate_state(
    session: Session,
    incoming_rows: Iterable[IncomingTransaction],
) -> ExistingDuplicateState:
    """Bulk-load active candidates for all target accounts in one query."""
    incoming = tuple(incoming_rows)
    account_ids = sorted({row.account_id for row in incoming})
    if not account_ids:
        return ExistingDuplicateState((), {}, {}, {})
    first_date = min(row.transaction_date for row in incoming)
    last_date = max(row.transaction_date for row in incoming)
    source_ids = sorted({
        row.source_transaction_id
        for row in incoming
        if row.source_transaction_id
    })
    identity_scope = [
        Transaction.transaction_date.between(first_date, last_date),
    ]
    if source_ids:
        identity_scope.append(Transaction.source_transaction_id.in_(source_ids))

    result = session.execute(
        select(
            Transaction.id,
            Transaction.account_id,
            Account.name.label("account_name"),
            Transaction.transaction_date,
            Transaction.description,
            Transaction.amount,
            Transaction.imported_at,
            Transaction.import_id,
            Transaction.source_transaction_id,
            Transaction.dedupe_fingerprint,
            Import.file_name,
            Import.content_hash,
        )
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Import, Import.id == Transaction.import_id)
        .where(
            Transaction.account_id.in_(account_ids),
            Transaction.is_deleted.is_(False),
            or_(*identity_scope),
        )
    ).all()

    snapshots = []
    for row in result:
        fingerprint = row.dedupe_fingerprint or build_transaction_fingerprint(
            row.account_id,
            row.transaction_date,
            row.description,
            row.amount,
        )
        snapshots.append(ExistingTransactionSnapshot(
            id=row.id,
            account_id=row.account_id,
            account_name=row.account_name,
            transaction_date=row.transaction_date,
            description=row.description,
            amount=row.amount,
            imported_at=row.imported_at,
            source_file=row.file_name,
            source_file_hash=row.content_hash,
            source_transaction_id=row.source_transaction_id,
            fingerprint=fingerprint,
            is_manual=row.import_id is None,
        ))

    by_source: dict[tuple[int, str], list[ExistingTransactionSnapshot]] = defaultdict(list)
    by_fingerprint: dict[str, list[ExistingTransactionSnapshot]] = defaultdict(list)
    by_file: dict[tuple[int, str, str], list[ExistingTransactionSnapshot]] = defaultdict(list)
    for row in snapshots:
        if row.source_transaction_id:
            by_source[(row.account_id, row.source_transaction_id)].append(row)
        by_fingerprint[row.fingerprint].append(row)
        if row.source_file_hash:
            by_file[(row.account_id, row.source_file_hash, row.fingerprint)].append(row)

    return ExistingDuplicateState(
        rows=tuple(snapshots),
        by_source_id={key: tuple(value) for key, value in by_source.items()},
        by_fingerprint={key: tuple(value) for key, value in by_fingerprint.items()},
        by_file_hash_and_fingerprint={
            key: tuple(value) for key, value in by_file.items()
        },
    )


def classify_import_rows(
    incoming_rows: Iterable[IncomingTransaction],
    existing_state: ExistingDuplicateState,
) -> DuplicateClassificationResult:
    """Classify a whole import batch with source-ID and occurrence-aware rules."""
    incoming = tuple(incoming_rows)
    new_rows: list[IncomingTransaction] = []
    definite: list[DefiniteDuplicate] = []
    possible: list[PossibleDuplicate] = []

    fallback_rows: list[tuple[int, IncomingTransaction]] = []
    stable_new_by_fingerprint: Counter[str] = Counter()
    seen_source_ids: set[tuple[int, str]] = set()
    candidate_number = 0

    # A byte-for-byte statement already tied to matching active rows is an
    # extremely strong row-level signal. Counts keep partial date imports safe.
    exact_file_remaining: Counter[tuple[int, str, str]] = Counter({
        key: len(matches)
        for key, matches in existing_state.by_file_hash_and_fingerprint.items()
    })

    for index, row in enumerate(incoming):
        file_identity = (
            row.account_id, row.source_file_hash, row.fingerprint
        )
        if exact_file_remaining[file_identity] > 0:
            exact_file_remaining[file_identity] -= 1
            definite.append(DefiniteDuplicate(
                row,
                "Matching occurrence from the same statement content was already imported.",
            ))
            continue
        source_id = (row.source_transaction_id or "").strip()
        if not source_id:
            fallback_rows.append((index, row))
            continue
        identity = (row.account_id, source_id)
        if identity in existing_state.by_source_id:
            definite.append(DefiniteDuplicate(
                row,
                "Same account and source transaction ID as an existing transaction.",
            ))
        elif identity in seen_source_ids:
            definite.append(DefiniteDuplicate(
                row,
                "Same account and source transaction ID as an earlier row in this batch.",
            ))
        else:
            seen_source_ids.add(identity)
            legacy_matches = tuple(
                match
                for match in existing_state.by_fingerprint.get(
                    row.fingerprint, ()
                )
                if match.source_transaction_id is None
            )
            if legacy_matches:
                candidate_number += 1
                possible.append(PossibleDuplicate(
                    candidate_id=f"duplicate-{candidate_number}-{index}",
                    incoming=row,
                    existing_matches=legacy_matches,
                    canonical_key=build_canonical_transaction_key(
                        row.account_id,
                        row.transaction_date,
                        row.description,
                        row.amount,
                    ),
                    reason=(
                        "Same account, date, normalized description and signed "
                        "amount as an existing transaction without a source ID."
                    ),
                ))
            else:
                new_rows.append(row)
                stable_new_by_fingerprint[row.fingerprint] += 1

    # If the same bytes were selected twice under different names, retain only
    # the first file's occurrences and classify later copies as definite.
    first_batch_file_for_hash: dict[tuple[int, str], str] = {}
    remaining: list[tuple[int, IncomingTransaction]] = []
    for index, row in fallback_rows:
        content_identity = (row.account_id, row.source_file_hash)
        first_file = first_batch_file_for_hash.setdefault(
            content_identity, row.batch_file_id
        )
        if row.batch_file_id != first_file:
            definite.append(DefiniteDuplicate(
                row,
                "Matching row from identical statement content appears earlier in this batch.",
            ))
        else:
            remaining.append((index, row))

    grouped: dict[str, list[tuple[int, IncomingTransaction]]] = defaultdict(list)
    for item in remaining:
        grouped[item[1].fingerprint].append(item)

    for fingerprint, group in grouped.items():
        existing_matches = existing_state.by_fingerprint.get(fingerprint, ())
        existing_count = len(existing_matches) + stable_new_by_fingerprint[fingerprint]
        per_file = Counter(row.batch_file_id for _, row in group)
        maximum_single_file_occurrences = max(per_file.values(), default=0)
        new_quota = max(0, maximum_single_file_occurrences - existing_count)
        possible_existing_quota = min(existing_count, len(group))

        for position, (original_index, row) in enumerate(group):
            if position < possible_existing_quota:
                classification = "possible"
                reason = "Same account, date, normalized description and signed amount."
            elif position < possible_existing_quota + new_quota:
                classification = "new"
                reason = ""
            else:
                classification = "possible"
                reason = (
                    "Same account, date, normalized description and signed amount "
                    "as an earlier occurrence in another selected statement."
                )

            if classification == "new":
                new_rows.append(row)
                continue
            candidate_number += 1
            possible.append(PossibleDuplicate(
                candidate_id=f"duplicate-{candidate_number}-{original_index}",
                incoming=row,
                existing_matches=existing_matches,
                canonical_key=build_canonical_transaction_key(
                    row.account_id,
                    row.transaction_date,
                    row.description,
                    row.amount,
                ),
                reason=reason,
            ))

    # Restore source-file order after grouping so summaries and review feel natural.
    order = {id(row): index for index, row in enumerate(incoming)}
    new_rows.sort(key=lambda row: order[id(row)])
    definite.sort(key=lambda item: order[id(item.incoming)])
    possible.sort(key=lambda item: order[id(item.incoming)])
    return DuplicateClassificationResult(
        new_rows=tuple(new_rows),
        definite_duplicates=tuple(definite),
        possible_duplicates=tuple(possible),
    )


def find_existing_duplicate_candidates(
    session: Session,
) -> tuple[ExistingDuplicateCandidate, ...]:
    """Report active fallback-key duplicates without modifying database rows."""
    rows = session.execute(
        select(
            Transaction.account_id,
            Account.name,
            Transaction.transaction_date,
            Transaction.description,
            Transaction.amount,
            Transaction.dedupe_fingerprint,
        )
        .join(Account, Account.id == Transaction.account_id)
        .where(Transaction.is_deleted.is_(False))
    ).all()
    grouped: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        fingerprint = row.dedupe_fingerprint or build_transaction_fingerprint(
            row.account_id, row.transaction_date, row.description, row.amount
        )
        grouped[fingerprint].append(row)
    return tuple(
        ExistingDuplicateCandidate(
            account_id=matches[0].account_id,
            account_name=matches[0].name,
            transaction_date=matches[0].transaction_date,
            description=matches[0].description,
            amount=matches[0].amount,
            count=len(matches),
        )
        for matches in grouped.values()
        if len(matches) > 1
    )
