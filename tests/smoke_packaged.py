"""Start a frozen app with isolated storage, then stop our test process."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def main() -> None:
    executable = Path(sys.argv[1]).resolve(strict=True)
    build_root = Path(__file__).resolve().parent.parent / "build"
    with tempfile.TemporaryDirectory(prefix="finance-smoke-", dir=build_root) as temp:
        isolated = Path(temp)
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        environment["LOCALAPPDATA"] = str(isolated / "local")
        environment["XDG_DATA_HOME"] = str(isolated / "xdg")
        database = (
            isolated / "local" / "Finance" / "finance.db"
            if sys.platform == "win32"
            else isolated / "xdg" / "finance" / "finance.db"
        )

        process = subprocess.Popen([str(executable)], env=environment)
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Packaged app exited early: {process.returncode}")
                if database.is_file():
                    break
                time.sleep(0.25)
            else:
                raise RuntimeError("Packaged app did not initialize its isolated database")

            time.sleep(2)
            if process.poll() is not None:
                raise RuntimeError(f"Packaged app exited after startup: {process.returncode}")
            print(f"Packaged app started and initialized isolated storage: {executable.name}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
