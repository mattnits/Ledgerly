# Ledgerly

Ledgerly is a private, easy-to-use finance tracker built with PySide6. The goal was to have one secure place to understand my spending trends, set financial goals, and track my investments, all without sending my financial data to the cloud. Everything stays offline on my computer, with as little manual input as possible. Ledgerly was created because I couldn't find an app with all the features, safety, and security requirements I wanted.

## Download and run

Download the Ledgerly release for your operating system:

- Windows: Download and double-click `LedgerlySetup.exe`. The installer adds Ledgerly to the Start menu, offers an optional desktop shortcut, and can launch the app when setup finishes. Administrator access is not required.
- Linux: Download and extract `Ledgerly-Linux.zip`, then open the extracted `Ledgerly` folder. If needed, run `chmod +x Ledgerly` once, then launch the app with `./Ledgerly` or from your desktop file manager.

The Windows and Linux downloads are separate, self-contained builds. They include Python and all required runtime packages, so users do **not** need to install Python, run `setup.bat`/`setup.sh`, or download anything else on first launch. The startup window shows setup progress while Ledgerly prepares local storage and its database; later launches use the same local data. A portable `Ledgerly-Windows-Portable.zip` is also available for Windows users who do not want to install the app; its executable and `_internal` folder must stay together. A GitHub source-code ZIP is not a prebuilt download.

The installer is currently unsigned, so Windows may show an “unrecognized app” SmartScreen warning for a newly downloaded build. Production releases should be signed with a consistent trusted publisher certificate.

Packaged builds store the database and saved imported statements in a writable user folder:

| Platform | Database location |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Ledgerly\finance.db` |
| Linux | `$XDG_DATA_HOME/ledgerly/finance.db`, or `~/.local/share/ledgerly/finance.db` when unset |

Imported statement copies are under `imported_statements` beside the database. Existing source-checkout data stays in its original location; it is **not** moved automatically into a packaged build. To carry it over, close Ledgerly first, back up your existing database, then copy it to the packaged location above.

On its first packaged launch, Ledgerly copies an existing legacy Finance profile into the new Ledgerly user-data folder when the Ledgerly folder does not yet exist. The legacy profile is left in place as a backup.

## Minimum requirements

- Windows 10 or 11, 64-bit; or 64-bit Linux with a graphical desktop, glibc 2.35 or newer (for example Ubuntu 22.04 or newer), and Qt's XCB runtime libraries.
- Permission to write to your user data folder. No network connection is needed after downloading the release ZIP.
- For running **from source only**: Python 3.11 or newer with `venv` and `pip`, plus the packages in `requirements.txt`: PySide6 (`>=6.8,<7`), QtAwesome (`>=1.3,<2`), and SQLAlchemy (`>=2,<3`). Their transitive dependencies are installed by pip. `pandas` and `matplotlib` are not required.

## Run from source

On Windows run `setup.bat`, then `.venv\Scripts\python.exe main.py`. On Linux run `bash setup.sh`, then `.venv/bin/python main.py`. Source runs keep using the existing `data/finance.db` location.

## Build desktop downloads

On each target operating system, install Python 3.11 or newer. To build the portable application, run:

```text
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm Ledgerly.spec
```

PyInstaller cannot cross-build the Windows download from Linux or vice versa.

For the Windows installer, install [Inno Setup 6](https://jrsoftware.org/isdl.php), then double-click `build-windows-installer.bat` or run it with an optional version:

```text
build-windows-installer.bat 1.0.0
```

This creates `dist/LedgerlySetup.exe`. It wraps the complete `dist/Ledgerly` PyInstaller bundle, installs under `%LOCALAPPDATA%\Programs\Ledgerly`, and does not delete the database or imported statements when upgrading or uninstalling.

### Automatic local Windows builds after commits

To rebuild Ledgerly after every local Git commit, enable the repository's hook once:

```text
git config --local core.hooksPath .githooks
```

After each commit on Windows, the hook runs `build-windows-installer.bat` and creates or updates `Ledgerly.lnk` in the repository root. The shortcut points to `dist\Ledgerly\Ledgerly.exe`. Generated builds and the machine-specific shortcut remain local and are not committed.

The `Build desktop downloads` GitHub Actions workflow builds and smoke-tests the portable applications and Windows installer. A `v*` tag publishes `LedgerlySetup.exe`, the Windows portable ZIP, and the Linux ZIP as release downloads; a manual workflow run keeps them as downloadable build artifacts.

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

Before the first launch after upgrading, make a normal backup copy of the SQLite database in the appropriate location above. Do not delete or recreate it. Then run Ledgerly; no separate migration command is required.

Work RRSP contribution history is derived at read time from non-deleted `INCOME`
transactions in the `Salary` category. The migration does not rewrite transactions,
create contribution rows, or alter portfolio snapshots. Editing a work RRSP rate
therefore recalculates its history without changing the source data.

## Tests

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m unittest discover -s tests -v
```
