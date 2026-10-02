# Finance

A local PySide6 finance app for importing statements, reviewing transactions, and tracking financial trends. The Investments page provides manual investment-account and portfolio-snapshot tracking; it does not connect to brokerages or external services.

## Run

```powershell
python main.py
```

## Investment schema migration

On startup, `init_db()` safely upgrades the original `investment_snapshots` table to the normalized investment schema when required:

- one `investment_accounts` row is created for each distinct legacy owner/account name;
- every legacy snapshot keeps its original ID, date, contribution, value, and user/group owner;
- legacy accounts use `Imported legacy data` as their institution so they are easy to identify and edit;
- account numbers retain their final seven alphanumeric characters only;
- installations that previously stored four masked digits preserve those digits in the new field;
- the old table is removed only after its rows have been copied inside the migration transaction.

Before the first launch after upgrading, make a normal backup copy of the SQLite database. Do not delete or recreate it. Then run `python main.py`; no separate migration command is required.

## Tests

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m unittest discover -s tests -v
```
