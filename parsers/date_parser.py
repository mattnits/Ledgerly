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


def parse_transaction_date(value: str) -> date:
    text = value.strip()
    if not text:
        raise ValueError("Date is empty")

    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass

    for date_format in DATE_FORMATS:
        for time_format in ("", *TIME_FORMATS):
            try:
                return datetime.strptime(text, date_format + time_format).date()
            except ValueError:
                continue

    raise ValueError(f"Unsupported date format: {text!r}")
