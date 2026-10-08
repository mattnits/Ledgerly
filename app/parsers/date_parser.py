import re
from collections.abc import Iterable
from datetime import date, datetime


DATE_FORMATS = (
    "%d/%m/%Y", "%d/%m/%y",
    "%d-%m-%Y", "%d-%m-%y",
    "%d.%m.%Y", "%d.%m.%y",
    "%d/%b/%Y", "%d/%B/%Y",
    "%d-%b-%Y", "%d-%B-%Y",
    "%d %b %Y", "%d %B %Y",
    "%Y/%m/%d", "%Y.%m.%d",
    "%m/%d/%Y", "%m/%d/%y",
)

TIME_FORMATS = (
    " %H:%M", " %H:%M:%S", " %H:%M:%S.%f",
    " %I:%M %p", " %I:%M:%S %p",
    "T%H:%M", "T%H:%M:%S", "T%H:%M:%S.%f",
)

SLASH_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(?:\d{2}|\d{4})(?:$|[ T])")


def infer_slash_month_first(values: Iterable[str], *, default_month_first: bool) -> bool:
    """Choose one slash-date order for a statement using unambiguous dates."""
    inferred = None
    for value in values:
        match = SLASH_DATE.match(value.strip())
        if match is None:
            continue
        first, second = map(int, match.groups())
        if first > 12 and second <= 12:
            month_first = False
        elif second > 12 and first <= 12:
            month_first = True
        else:
            continue
        if inferred is not None and inferred != month_first:
            raise ValueError("Conflicting slash date formats in statement")
        inferred = month_first
    return default_month_first if inferred is None else inferred


def parse_transaction_date(value: str, *, month_first: bool = False) -> date:
    text = value.strip()
    if not text:
        raise ValueError("Date is empty")

    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass

    formats = DATE_FORMATS
    if month_first:
        formats = ("%m/%d/%Y", "%m/%d/%y") + tuple(
            fmt for fmt in DATE_FORMATS if fmt not in ("%m/%d/%Y", "%m/%d/%y")
        )
    for date_format in formats:
        for time_format in ("", *TIME_FORMATS):
            try:
                return datetime.strptime(text, date_format + time_format).date()
            except ValueError:
                continue

    raise ValueError(f"Unsupported date format: {text!r}")
