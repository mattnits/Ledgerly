"""Paths for source checkouts and self-contained desktop builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_data_dir() -> Path:
    """Keep source-checkout data in place; use user storage for packaged builds."""
    if not is_packaged():
        return Path(__file__).resolve().parent.parent / "data"

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
