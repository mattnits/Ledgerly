"""Paths for source checkouts and self-contained desktop builds."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
DATA_DIR = PROJECT_ROOT / "data"
ASSETS_DIR = PROJECT_ROOT / "assets"
ICONS_DIR = ASSETS_DIR / "icons"


def is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_data_dir() -> Path:
    """Keep source-checkout data in place; use user storage for packaged builds."""
    if not is_packaged():
        return DATA_DIR

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return root / "Ledgerly"

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    root = Path(xdg_data_home) if xdg_data_home and Path(xdg_data_home).is_absolute() else Path.home() / ".local" / "share"
    return root / "ledgerly"


def prepare_app_data_dir() -> Path:
    """Create Ledgerly's storage, copying a legacy Finance profile once."""
    target = app_data_dir()
    if target.exists():
        return target

    legacy = _legacy_app_data_dir()
    if legacy is not None and legacy.is_dir():
        shutil.copytree(legacy, target)
    else:
        target.mkdir(parents=True, exist_ok=True)
    return target


def _legacy_app_data_dir() -> Path | None:
    if not is_packaged():
        return None

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return root / "Finance"

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    root = Path(xdg_data_home) if xdg_data_home and Path(xdg_data_home).is_absolute() else Path.home() / ".local" / "share"
    return root / "finance"


def import_archive_dir() -> Path:
    return app_data_dir() / "imported_statements"


def import_archive_label() -> str:
    if is_packaged():
        return str(import_archive_dir())
    return "data/imported_statements"
