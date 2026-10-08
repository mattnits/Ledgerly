# Finance

A local PySide6 finance app for importing statements, reviewing transactions, and tracking financial trends. The Investments page provides manual investment-account and portfolio-snapshot tracking; it does not connect to brokerages or external services.

## Download and run

Download the release ZIP for your operating system, extract the **entire** `Finance` folder, and start the application from inside it:

- Windows: double-click `Finance.exe`.
- Linux: run `chmod +x Finance` once if needed, then run `./Finance` from a terminal or desktop file manager.

The Windows and Linux downloads are separate, self-contained builds. They include Python and the three runtime packages, so users do **not** need to install Python, run `setup.bat`/`setup.sh`, or download packages on first launch. The startup window shows setup progress while Finance prepares local storage and its database; later launches open the same way without reinstalling anything. Keep the executable and its `_internal` folder together. A GitHub source-code ZIP is not a prebuilt download.

Packaged builds store the database and saved imported statements in a writable user folder:

| Platform | Database location |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Finance\finance.db` |
| Linux | `$XDG_DATA_HOME/finance/finance.db`, or `~/.local/share/finance/finance.db` when unset |

Imported statement copies are under `imported_statements` beside the database. Existing source-checkout data stays in its original location; it is **not** moved automatically into a packaged build. To carry it over, close Finance first, back up your existing database, then copy it to the packaged location above.

## Minimum requirements

- Windows 10 or 11, 64-bit; or 64-bit Linux with a graphical desktop, glibc 2.35 or newer (for example Ubuntu 22.04 or newer), and Qt's XCB runtime libraries.
- Permission to write to your user data folder. No network connection is needed after downloading the release ZIP.
- For running **from source only**: Python 3.11 or newer with `venv` and `pip`, plus the packages in `requirements.txt`: PySide6 (`>=6.8,<7`), QtAwesome (`>=1.3,<2`), and SQLAlchemy (`>=2,<3`). Their transitive dependencies are installed by pip. `pandas` and `matplotlib` are not required.

## Run from source

On Windows run `setup.bat`, then `.venv\Scripts\python.exe main.py`. On Linux run `bash setup.sh`, then `.venv/bin/python main.py`. Source runs keep using the existing `data/finance.db` location.

## Build desktop downloads

On each target operating system, install Python 3.11 or newer and run:

```text
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm Finance.spec
```

Distribute the **whole** `dist/Finance` folder, or zip that folder. Windows produces `Finance.exe`; Linux produces an executable named `Finance` (Linux does not run `.exe` files). PyInstaller cannot cross-build the Windows download from Linux or vice versa. The `Build desktop downloads` GitHub Actions workflow tests and builds both platforms. A `v*` tag publishes the ZIPs as release downloads; a manual workflow run keeps them as downloadable build artifacts.

## Investment schema migration

On startup, `init_db()` safely upgrades the original `investment_snapshots` table to the normalized investment schema when required:

- one `investment_accounts` row is created for each distinct legacy owner/account name;
- every legacy snapshot keeps its original ID, date, contribution, value, and user/group owner;
- legacy accounts use `Imported legacy data` as their institution so they are easy to identify and edit;
- account numbers retain their final seven alphanumeric characters only;
- installations that previously stored four masked digits preserve those digits in the new field;
- work RRSP configuration columns are added in place with `false`/`NULL`
  defaults, so no existing RRSP is opted in automatically;
- the old table is removed only after its rows have been copied inside the migration transaction.

Before the first launch after upgrading, make a normal backup copy of the SQLite database in the appropriate location above. Do not delete or recreate it. Then run Finance; no separate migration command is required.

Work RRSP contribution history is derived at read time from non-deleted `INCOME`
transactions in the `Salary` category. The migration does not rewrite transactions,
create contribution rows, or alter portfolio snapshots. Editing a work RRSP rate
therefore recalculates its history without changing the source data.

## Tests

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m unittest discover -s tests -v
```
