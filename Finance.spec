# Build separately on Windows and Linux: python -m PyInstaller --noconfirm Finance.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


project_root = Path(SPECPATH)
assets = [(str(project_root / "assets" / "icons"), "assets/icons")]
assets += collect_data_files("qtawesome")

analysis = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=assets,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
archive = PYZ(analysis.pure)
program = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Finance",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
bundle = COLLECT(
    program,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="Finance",
)
