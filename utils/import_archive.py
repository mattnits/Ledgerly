from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from utils.app_paths import import_archive_dir

IMPORT_ARCHIVE_ROOT = import_archive_dir()


@dataclass
class StagedImportArchive:
    """A copied statement batch that becomes visible only after import succeeds."""

    staging_path: Path
    final_path: Path

    def commit(self) -> Path:
        self.staging_path.rename(self.final_path)
        return self.final_path

    def discard(self) -> None:
        if self.staging_path.exists():
            shutil.rmtree(self.staging_path)


def stage_import_files(
    filenames: list[str],
    *,
    destination_root: Path = IMPORT_ARCHIVE_ROOT,
) -> StagedImportArchive:
    """Copy every selected file into one staging batch, or keep none of them."""
    sources = [Path(filename).resolve(strict=True) for filename in filenames]
    if not sources:
        raise ValueError("Select at least one file to archive")
    if any(not source.is_file() for source in sources):
        raise ValueError("Every archived statement must be a file")

    destination_root.mkdir(parents=True, exist_ok=True)
    batch_name = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
    staging_path = destination_root / f".{batch_name}.tmp"
    final_path = destination_root / batch_name
    staging_path.mkdir()
    archive = StagedImportArchive(staging_path, final_path)

    used_names: set[str] = set()
    try:
        for source in sources:
            destination_name = source.name
            counter = 2
            while destination_name.casefold() in used_names:
                destination_name = f"{source.stem}_{counter}{source.suffix}"
                counter += 1
            used_names.add(destination_name.casefold())
            shutil.copy2(source, staging_path / destination_name)
    except Exception:
        archive.discard()
        raise
    return archive
