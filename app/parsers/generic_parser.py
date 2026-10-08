from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import html
from io import StringIO
from pathlib import Path
import sys
import traceback

from sqlalchemy import select

from app.services.category_rules import category_rules_for_user, classify_description
from app.core.db import SessionLocal
from app.services.deduplication import (
    DuplicateClassificationResult,
    DuplicateDecision,
    IncomingTransaction,
    PossibleDuplicate,
    classify_import_rows,
    load_existing_duplicate_state,
)
from app.models.models import Account, Import, Transaction, User
from app.parsers.date_parser import infer_slash_month_first, parse_transaction_date
from app.utils.constants import SUPPORTED_PARSE_TYPES


AMEX_COLUMNS = (
    "Date", "Date Processed", "Description", "Amount",
    "Foreign Spend Amount", "Commission", "Exchange Rate",
    "Additional Information", "Merchant", "Address", "City / Province",
    "Postal Code", "Country", "Reference",
)
TD_QUOTE_TRANSLATION = str.maketrans("", "", "\"'â€œâ€â€˜â€™")
AMEX_SHORT_COLUMNS = (
    "Date", "Date Processed", "Description", "Amount",
)


def detect_amex_format(fieldnames: list[str] | None) -> str:
    normalized = normalize_amex_fieldnames(fieldnames)
    column_count = len(normalized)
    if column_count == len(AMEX_SHORT_COLUMNS):
        if normalized == list(AMEX_SHORT_COLUMNS):
            return "short"
    elif column_count > len(AMEX_SHORT_COLUMNS):
        if set(AMEX_SHORT_COLUMNS).issubset(normalized):
            return "full"
    raise ValueError(
        "Amex CSV columns do not match the full or short expected format"
    )


def normalize_amex_fieldnames(fieldnames: list[str] | None) -> list[str]:
    if not fieldnames:
        return []
    normalized = [html.unescape(name).strip().lstrip("\ufeff") for name in fieldnames]
    if len(normalized) != len(set(normalized)):
        raise ValueError("Amex CSV contains duplicate column names")
    return normalized


def parse_money(value: str) -> Decimal:
    text = value.strip().replace(",", "").replace("$", "")
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    amount = Decimal(text)
    if not amount.is_finite() or amount.as_tuple().exponent < -2:
        raise ValueError("Value must have at most two decimal places")
    return amount


@dataclass
class ImportSummary:
    parsed: int = 0
    added: int = 0
    definite_duplicates_skipped: int = 0
    possible_duplicates: int = 0
    possible_kept: int = 0
    possible_skipped: int = 0
    failed: int = 0


@dataclass
class _ParsedRow:
    transaction_date: date
    description: str
    amount: Decimal
    source_transaction_id: str | None = None


@dataclass
class _ParsedFile:
    filepath: str
    statement_type: SUPPORTED_PARSE_TYPES
    content_hash: str
    batch_file_id: str
    rows: list[_ParsedRow]
    latest_balance_date: date | None = None
    latest_balance: Decimal | None = None
    account_id: int | None = None


class GenericParser:
    """Parse statements, commit definite-new rows, and retain review rows in memory."""

    def __init__(
        self,
        file_data: list[tuple[str, str]],
        user_id: str | None = None,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> None:
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValueError("The import start date must be on or before the end date")
        self.file_data = file_data
        self.user_id = user_id
        self.start_date = start_date
        self.end_date = end_date
        self._errors: list[tuple[str, str]] = []
        self._skipped_lines: list[tuple[str, int, str]] = []
        self._classification = DuplicateClassificationResult((), (), ())
        self._summary = ImportSummary()
        self._import_ids: dict[str, int] = {}
        self._parsed_files: dict[str, _ParsedFile] = {}
        self._session_factory = SessionLocal

    def _date_is_selected(self, transaction_date: date) -> bool:
        return not (
            (self.start_date is not None and transaction_date < self.start_date)
            or (self.end_date is not None and transaction_date > self.end_date)
        )

    def _empty_import_message(self, statement_name: str) -> str:
        if self.start_date is not None or self.end_date is not None:
            return f"{statement_name} contains no transactions in the selected date range"
        return f"{statement_name} contains no transactions"

    def parse(self) -> None:
        # Capture the factory used for this batch so deferred review commits use
        # the same database/session configuration.
        self._session_factory = SessionLocal
        self._errors = []
        self._skipped_lines = []
        self._classification = DuplicateClassificationResult((), (), ())
        self._summary = ImportSummary()
        self._import_ids = {}
        self._parsed_files = {}

        parsed_files: list[_ParsedFile] = []
        for file_index, (filepath, statement_type) in enumerate(self.file_data):
            try:
                selected_type = SUPPORTED_PARSE_TYPES(statement_type)
                batch_file_id = f"file-{file_index}"
                if selected_type in (
                    SUPPORTED_PARSE_TYPES.TD_CREDIT,
                    SUPPORTED_PARSE_TYPES.TD_DEBIT,
                ):
                    parsed = self._read_td(filepath, selected_type, batch_file_id)
                elif selected_type == SUPPORTED_PARSE_TYPES.AMEX:
                    parsed = self._read_amex(filepath, batch_file_id)
                else:
                    raise ValueError(f"Unsupported parse type: {statement_type}")
                parsed_files.append(parsed)
            except Exception as exc:
                self._record_file_error(filepath, exc)

        if not parsed_files:
            self._summary.failed = len(self._errors) + len(self._skipped_lines)
            return

        try:
            with self._session_factory.begin() as session:
                if self.user_id is None or session.get(User, self.user_id) is None:
                    raise ValueError("Select an existing user before importing statements")
                accounts = list(session.scalars(
                    select(Account).where(Account.user_id == self.user_id)
                ).all())
                rules = category_rules_for_user(session, self.user_id)
                incoming: list[IncomingTransaction] = []

                for parsed in parsed_files:
                    try:
                        account = self._resolve_account(session, accounts, parsed)
                    except Exception as exc:
                        self._record_file_error(parsed.filepath, exc)
                        continue
                    parsed.account_id = account.id
                    self._parsed_files[parsed.batch_file_id] = parsed
                    for row in parsed.rows:
                        assignment = classify_description(
                            row.description, rules, account.id
                        )
                        incoming.append(IncomingTransaction(
                            account_id=account.id,
                            account_name=account.name,
                            transaction_date=row.transaction_date,
                            description=row.description,
                            amount=row.amount,
                            source_file=Path(parsed.filepath).name,
                            source_file_hash=parsed.content_hash,
                            batch_file_id=parsed.batch_file_id,
                            source_transaction_id=row.source_transaction_id,
                            payload={
                                "transaction_type": assignment.transaction_type,
                                "category_id": assignment.category_id,
                                "classification_source": assignment.classification_source,
                            },
                        ))

                state = load_existing_duplicate_state(session, incoming)
                self._classification = classify_import_rows(incoming, state)
                for row in self._classification.new_rows:
                    import_record = self._import_record_for(session, row)
                    session.add(self._transaction_model(row, import_record))

                for parsed in self._parsed_files.values():
                    if parsed.latest_balance_date is None or parsed.account_id is None:
                        continue
                    account = session.get(Account, parsed.account_id)
                    if account is not None and (
                        account.balance_as_of is None
                        or parsed.latest_balance_date >= account.balance_as_of
                    ):
                        account.balance = parsed.latest_balance
                        account.balance_as_of = parsed.latest_balance_date
                session.flush()
        except Exception as exc:
            for parsed in parsed_files:
                if not any(path == parsed.filepath for path, _ in self._errors):
                    self._record_file_error(parsed.filepath, exc)
            self._classification = DuplicateClassificationResult((), (), ())

        self._summary = ImportSummary(
            parsed=sum(len(item.rows) for item in parsed_files),
            added=len(self._classification.new_rows),
            definite_duplicates_skipped=len(
                self._classification.definite_duplicates
            ),
            possible_duplicates=len(self._classification.possible_duplicates),
            failed=len(self._errors) + len(self._skipped_lines),
        )

    def _read_td(
        self,
        filepath: str,
        statement_type: SUPPORTED_PARSE_TYPES,
        batch_file_id: str,
    ) -> _ParsedFile:
        if Path(filepath).suffix.casefold() != ".csv":
            raise ValueError("TD statements must be CSV files")
        if self.user_id is None:
            raise ValueError("Select a user before importing a TD statement")
        raw = self._open_file_contents(filepath)
        content_hash = hashlib.sha256(raw).hexdigest()
        try:
            contents = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            contents = raw.decode("cp1252")
        reader = csv.reader(StringIO(contents, newline=""))
        raw_rows = [(reader.line_num, row) for row in reader]
        month_first = infer_slash_month_first(
            (row[0].translate(TD_QUOTE_TRANSLATION) for _, row in raw_rows if row),
            default_month_first=statement_type == SUPPORTED_PARSE_TYPES.TD_CREDIT,
        )
        rows: list[_ParsedRow] = []
        latest_balance_date = None
        latest_balance = None
        for line_number, raw_row in raw_rows:
            row = [field.translate(TD_QUOTE_TRANSLATION) for field in raw_row]
            if not row or all(not field.strip() for field in row):
                continue
            try:
                if len(row) not in (3, 4, 5):
                    raise ValueError(
                        "Expected date, description, amount, optional balance; "
                        "or date, description, withdrawal, deposit, balance"
                    )
                transaction_date = parse_transaction_date(
                    row[0], month_first=month_first
                )
                if not self._date_is_selected(transaction_date):
                    continue
                description = row[1].strip()
                if not description or len(description) > 255:
                    raise ValueError("Description must be 1 to 255 characters")
                if len(row) == 5:
                    withdrawal, deposit = row[2].strip(), row[3].strip()
                    if bool(withdrawal) == bool(deposit):
                        raise ValueError(
                            "Exactly one of withdrawal or deposit must have an amount"
                        )
                    amount = (
                        -abs(parse_money(withdrawal))
                        if withdrawal
                        else abs(parse_money(deposit))
                    )
                    balance = parse_money(row[4]) if row[4].strip() else None
                else:
                    amount = parse_money(row[2])
                    balance = (
                        parse_money(row[3])
                        if len(row) == 4 and row[3].strip()
                        else None
                    )
            except (ValueError, InvalidOperation, TypeError) as exc:
                self._skip_line(filepath, line_number, exc)
                continue
            rows.append(_ParsedRow(transaction_date, description, amount))
            if balance is not None and (
                latest_balance_date is None or transaction_date > latest_balance_date
            ):
                latest_balance_date = transaction_date
                latest_balance = balance
        if not rows:
            raise ValueError(self._empty_import_message("TD CSV"))
        return _ParsedFile(
            filepath=filepath,
            statement_type=statement_type,
            content_hash=content_hash,
            batch_file_id=batch_file_id,
            rows=rows,
            latest_balance_date=latest_balance_date,
            latest_balance=latest_balance,
        )

    def _read_amex(self, filepath: str, batch_file_id: str) -> _ParsedFile:
        if self.user_id is None:
            raise ValueError("Select a user before importing an Amex statement")
        raw = self._open_file_contents(filepath)
        content_hash = hashlib.sha256(raw).hexdigest()
        try:
            contents = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            contents = raw.decode("cp1252")
        reader = csv.DictReader(StringIO(contents, newline=""))
        normalized_fieldnames = normalize_amex_fieldnames(reader.fieldnames)
        amex_format = detect_amex_format(normalized_fieldnames)
        reader.fieldnames = normalized_fieldnames
        raw_rows = [(reader.line_num, row) for row in reader]
        month_first = infer_slash_month_first(
            (row["Date"] for _, row in raw_rows if row.get("Date")),
            default_month_first=False,
        )
        rows: list[_ParsedRow] = []
        for line_number, row in raw_rows:
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(
                        f"Wrong number of columns for {amex_format} Amex format"
                    )
                transaction_date = parse_transaction_date(
                    row["Date"], month_first=month_first
                )
                if not self._date_is_selected(transaction_date):
                    continue
                description = row["Description"].strip()
                if not description or len(description) > 255:
                    raise ValueError("Description must be 1 to 255 characters")
                amount = -parse_money(row["Amount"])
                source_id = (row.get("Reference") or "").strip() or None
            except (ValueError, InvalidOperation, TypeError) as exc:
                self._skip_line(filepath, line_number, exc)
                continue
            rows.append(_ParsedRow(
                transaction_date,
                description,
                amount,
                source_transaction_id=source_id,
            ))
        if not rows:
            raise ValueError(self._empty_import_message("Amex CSV"))
        return _ParsedFile(
            filepath=filepath,
            statement_type=SUPPORTED_PARSE_TYPES.AMEX,
            content_hash=content_hash,
            batch_file_id=batch_file_id,
            rows=rows,
        )

    def _resolve_account(
        self,
        session,
        accounts: list[Account],
        parsed: _ParsedFile,
    ) -> Account:
        if parsed.statement_type in (
            SUPPORTED_PARSE_TYPES.TD_CREDIT,
            SUPPORTED_PARSE_TYPES.TD_DEBIT,
        ):
            account_type = (
                "credit"
                if parsed.statement_type == SUPPORTED_PARSE_TYPES.TD_CREDIT
                else "debit"
            )
            matches = [
                account for account in accounts
                if "td" in account.institution.casefold()
                and account.account_type == account_type
            ]
            if len(matches) > 1:
                raise ValueError(
                    f"The current user has multiple TD {account_type} accounts"
                )
            if matches:
                return matches[0]
            account = Account(
                user_id=self.user_id,
                name=f"TD {account_type.title()}",
                institution="TD",
                account_type=account_type,
            )
        else:
            matches = [
                account for account in accounts
                if "amex" in account.institution.casefold()
                or "american express" in account.institution.casefold()
            ]
            if len(matches) > 1:
                raise ValueError("The current user has multiple Amex accounts")
            if matches:
                return matches[0]
            account = Account(
                user_id=self.user_id,
                name="American Express",
                institution="American Express",
                account_type="credit",
            )
        session.add(account)
        session.flush()
        accounts.append(account)
        return account

    def _import_record_for(self, session, row: IncomingTransaction) -> Import:
        import_id = self._import_ids.get(row.batch_file_id)
        if import_id is not None:
            record = session.get(Import, import_id)
            if record is not None:
                return record
        record = Import(
            account_id=row.account_id,
            file_name=row.source_file,
            content_hash=row.source_file_hash,
        )
        session.add(record)
        session.flush()
        self._import_ids[row.batch_file_id] = record.id
        return record

    @staticmethod
    def _transaction_model(
        row: IncomingTransaction,
        import_record: Import,
    ) -> Transaction:
        return Transaction(
            account_id=row.account_id,
            import_record=import_record,
            transaction_date=row.transaction_date,
            description=row.description,
            amount=row.amount,
            transaction_type=row.payload.get("transaction_type"),
            category_id=row.payload.get("category_id"),
            classification_source=row.payload.get("classification_source"),
            source_transaction_id=row.source_transaction_id,
            dedupe_fingerprint=row.fingerprint,
        )

    def get_possible_duplicates(self) -> list[PossibleDuplicate]:
        return list(self._classification.possible_duplicates)

    def get_duplicate_result(self) -> DuplicateClassificationResult:
        return self._classification

    def set_duplicate_decision(
        self,
        candidate_id: str,
        decision: DuplicateDecision | str,
    ) -> None:
        resolved = DuplicateDecision(decision)
        for candidate in self._classification.possible_duplicates:
            if candidate.candidate_id == candidate_id:
                candidate.decision = resolved
                return
        raise KeyError(f"Unknown duplicate candidate: {candidate_id}")

    def set_all_duplicate_decisions(
        self,
        decision: DuplicateDecision | str,
    ) -> None:
        resolved = DuplicateDecision(decision)
        for candidate in self._classification.possible_duplicates:
            candidate.decision = resolved

    def commit_duplicate_decisions(self) -> ImportSummary:
        candidates = self._classification.possible_duplicates
        unresolved = [
            item for item in candidates
            if item.decision == DuplicateDecision.UNRESOLVED
        ]
        if unresolved:
            raise ValueError("Resolve every possible duplicate before importing")
        keepers = [
            item.incoming for item in candidates
            if item.decision == DuplicateDecision.KEEP
        ]
        if keepers:
            with self._session_factory.begin() as session:
                for row in keepers:
                    import_record = self._import_record_for(session, row)
                    session.add(self._transaction_model(row, import_record))
                session.flush()
        self._summary.added += len(keepers)
        self._summary.possible_kept = len(keepers)
        self._summary.possible_skipped = len(candidates) - len(keepers)
        return self._summary

    def get_import_summary(self) -> ImportSummary:
        return self._summary

    def get_results(self) -> list[tuple[str, str]]:
        return self._errors

    def _already_imported(self, session, content_hash: str) -> bool:
        return session.scalar(
            select(Import.id)
            .join(Account, Import.account_id == Account.id)
            .where(
                Account.user_id == self.user_id,
                Import.content_hash == content_hash,
            )
            .limit(1)
        ) is not None

    def get_skipped_lines(self) -> list[tuple[str, int, str]]:
        return self._skipped_lines

    def _record_file_error(self, filepath: str, exc: Exception) -> None:
        message = str(exc) or type(exc).__name__
        print(f"Failed to parse {filepath}: {message}", file=sys.stderr)
        traceback.print_exc()
        self._errors.append((filepath, message))

    def _skip_line(self, filepath: str, line_number: int, exc: Exception) -> None:
        message = str(exc) or type(exc).__name__
        self._skipped_lines.append((filepath, line_number, message))
        print(f"Skipping {filepath} line {line_number}: {message}", file=sys.stderr)

    def _open_file_contents(self, filepath: str) -> bytes:
        with open(filepath, "rb") as file:
            return file.read()
