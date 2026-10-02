import csv
import hashlib
import html
import sys
import traceback
from datetime import date
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path

from sqlalchemy import or_, select

from utils.constants import SUPPORTED_PARSE_TYPES
from database.db import SessionLocal
from database.category_rules import category_rules_for_user, classify_description
from database.models import Account, Import, Transaction, User
from parsers.date_parser import infer_slash_month_first, parse_transaction_date



AMEX_COLUMNS = (
    "Date", "Date Processed", "Description", "Amount",
    "Foreign Spend Amount", "Commission", "Exchange Rate",
    "Additional Information", "Merchant", "Address", "City / Province",
    "Postal Code", "Country", "Reference",
)
TD_QUOTE_TRANSLATION = str.maketrans("", "", "\"'“”‘’")


AMEX_SHORT_COLUMNS = (
    "Date", "Date Processed", "Description", "Amount",
)


def detect_amex_format(fieldnames: list[str] | None) -> str:
    normalized = normalize_amex_fieldnames(fieldnames)
    column_count = len(normalized)

    # Amex's compact export has four columns. Detailed exports contain those
    # same transaction fields plus additional metadata, so the header width is
    # enough to select the variant before validating its required columns.
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


class GenericParser:
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
        self._errors = []
        self._skipped_lines = []
        for filepath, statement_type in self.file_data:
            try:
                selected_type = SUPPORTED_PARSE_TYPES(statement_type)
                match selected_type:
                    case SUPPORTED_PARSE_TYPES.TD_CREDIT | SUPPORTED_PARSE_TYPES.TD_DEBIT:
                        self._parse_td(filepath, selected_type)
                    case SUPPORTED_PARSE_TYPES.AMEX:
                        self._parse_amex(filepath)
                    case _:
                        raise ValueError(f"Unsupported parse type: {statement_type}")
            except Exception as exc:
                message = str(exc) or type(exc).__name__
                print(f"Failed to parse {filepath}: {message}", file=sys.stderr)
                traceback.print_exc()
                self._errors.append((filepath, message))

    def _parse_td(self, filepath: str, statement_type: SUPPORTED_PARSE_TYPES) -> None:
        if statement_type not in (SUPPORTED_PARSE_TYPES.TD_CREDIT, SUPPORTED_PARSE_TYPES.TD_DEBIT):
            raise ValueError(f"Unsupported TD parse type: {statement_type}")
        account_type = "credit" if statement_type == SUPPORTED_PARSE_TYPES.TD_CREDIT else "debit"
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
        rows = [(reader.line_num, row) for row in reader]
        month_first = infer_slash_month_first(
            (row[0].translate(TD_QUOTE_TRANSLATION) for _, row in rows if row),
            default_month_first=statement_type == SUPPORTED_PARSE_TYPES.TD_CREDIT,
        )

        with SessionLocal.begin() as session:
            if self._already_imported(session, content_hash):
                return
            accounts = session.scalars(
                select(Account).where(
                    Account.user_id == self.user_id,
                    Account.institution.ilike("%td%"),
                    Account.account_type == account_type,
                )
            ).all()
            if len(accounts) > 1:
                raise ValueError(f"The current user has multiple TD {account_type} accounts")
            if accounts:
                account = accounts[0]
            else:
                if session.get(User, self.user_id) is None:
                    raise ValueError("The selected user no longer exists")
                account = Account(
                    user_id=self.user_id,
                    name=f"TD {account_type.title()}",
                    institution="TD",
                    account_type=account_type,
                )
                session.add(account)
                session.flush()

            category_rules = category_rules_for_user(session, self.user_id)
            import_record = Import(
                account_id=account.id,
                file_name=Path(filepath).name,
                content_hash=content_hash,
            )
            session.add(import_record)
            session.flush()

            row_count = 0
            latest_balance_date = None
            latest_balance = None
            for line_number, row in rows:
                row = [field.translate(TD_QUOTE_TRANSLATION) for field in row]
                if not row or all(not field.strip() for field in row):
                    continue
                try:
                    if len(row) not in (3, 4, 5):
                        raise ValueError(
                            "Expected date, description, amount, optional balance; "
                            "or date, description, withdrawal, deposit, balance"
                        )
                    transaction_date = parse_transaction_date(row[0], month_first=month_first)
                    if not self._date_is_selected(transaction_date):
                        continue
                    description = row[1].strip()
                    if not description or len(description) > 255:
                        raise ValueError("Description must be 1 to 255 characters")
                    if len(row) == 5:
                        withdrawal, deposit = row[2].strip(), row[3].strip()
                        if bool(withdrawal) == bool(deposit):
                            raise ValueError("Exactly one of withdrawal or deposit must have an amount")
                        amount = -abs(parse_money(withdrawal)) if withdrawal else abs(parse_money(deposit))
                        balance = parse_money(row[4]) if row[4].strip() else None
                    else:
                        amount = parse_money(row[2])
                        balance = parse_money(row[3]) if len(row) == 4 and row[3].strip() else None
                except (ValueError, InvalidOperation, TypeError) as exc:
                    self._skip_line(filepath, line_number, exc)
                    continue

                assignment = classify_description(
                    description,
                    category_rules,
                    account.id,
                )
                session.add(Transaction(
                    account_id=account.id,
                    import_record=import_record,
                    transaction_date=transaction_date,
                    description=description,
                    amount=amount,
                    transaction_type=assignment.transaction_type,
                    category_id=assignment.category_id,
                    classification_source=assignment.classification_source,
                ))
                row_count += 1
                if balance is not None and (
                    latest_balance_date is None or transaction_date > latest_balance_date
                ):
                    latest_balance_date = transaction_date
                    latest_balance = balance

            if row_count == 0:
                raise ValueError(self._empty_import_message("TD CSV"))
            if latest_balance_date is not None and (
                account.balance_as_of is None or latest_balance_date >= account.balance_as_of
            ):
                account.balance = latest_balance
                account.balance_as_of = latest_balance_date
            session.flush()

    def _parse_amex(self, filepath: str) -> None:
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
        rows = [(reader.line_num, row) for row in reader]
        month_first = infer_slash_month_first(
            (row["Date"] for _, row in rows if row.get("Date")),
            default_month_first=False,
        )

        if self.user_id is None:
            raise ValueError("Select a user before importing an Amex statement")

        with SessionLocal.begin() as session:
            if self._already_imported(session, content_hash):
                return
            account_ids = session.scalars(
                select(Account.id).where(
                    Account.user_id == self.user_id,
                    or_(
                        Account.institution.ilike("%amex%"),
                        Account.institution.ilike("%american express%"),
                    ),
                )
            ).all()
            if not account_ids:
                if session.get(User, self.user_id) is None:
                    raise ValueError("The selected user no longer exists")
                account = Account(
                    user_id=self.user_id,
                    name="American Express",
                    institution="American Express",
                    account_type="credit",
                )
                session.add(account)
                session.flush()
                account_ids = [account.id]
            if len(account_ids) > 1:
                raise ValueError("The current user has multiple Amex accounts")
            account_id = account_ids[0]
            category_rules = category_rules_for_user(session, self.user_id)

            import_record = Import(
                account_id=account_id,
                file_name=Path(filepath).name,
                content_hash=content_hash,
            )
            session.add(import_record)
            session.flush()

            row_count = 0
            for line_number, row in rows:
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
                except (ValueError, InvalidOperation, TypeError) as exc:
                    self._skip_line(filepath, line_number, exc)
                    continue

                assignment = classify_description(
                    description,
                    category_rules,
                    account_id,
                )
                session.add(Transaction(
                    account_id=account_id,
                    import_record=import_record,
                    transaction_date=transaction_date,
                    description=description,
                    amount=amount,
                    transaction_type=assignment.transaction_type,
                    category_id=assignment.category_id,
                    classification_source=assignment.classification_source,
                ))
                row_count += 1

            if row_count == 0:
                raise ValueError(self._empty_import_message("Amex CSV"))
            session.flush()

    def get_results(self) -> list[tuple[str, str]]:
        return self._errors

    def _already_imported(self, session, content_hash: str) -> bool:
        return session.scalar(
            select(Import.id)
            .join(Account, Import.account_id == Account.id)
            .where(Account.user_id == self.user_id, Import.content_hash == content_hash)
            .limit(1)
        ) is not None

    def get_skipped_lines(self) -> list[tuple[str, int, str]]:
        return self._skipped_lines

    def _skip_line(self, filepath: str, line_number: int, exc: Exception) -> None:
        message = str(exc) or type(exc).__name__
        self._skipped_lines.append((filepath, line_number, message))
        print(f"Skipping {filepath} line {line_number}: {message}", file=sys.stderr)

    def _open_file_contents(self, filepath: str) -> bytes:
        with open(filepath, "rb") as file:
            return file.read()
