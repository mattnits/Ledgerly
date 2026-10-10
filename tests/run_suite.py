"""Run the full test suite and shut down Qt worker threads cleanly."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _finish_qt_work() -> bool:
    """Drain deferred Qt cleanup and stop idle global thread-pool threads."""
    from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool

    thread_pool = QThreadPool.globalInstance()
    if not thread_pool.waitForDone(5_000):
        return False

    application = QCoreApplication.instance()
    if application is not None:
        application.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        application.processEvents()

    # Processing a completed worker's queued signal can schedule a follow-up
    # query, so wait once more before allowing Python to tear Qt down.
    return thread_pool.waitForDone(5_000)


def main() -> int:
    suite = unittest.defaultTestLoader.discover(str(PROJECT_ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    if not _finish_qt_work():
        print(
            "Qt worker threads did not stop within five seconds.",
            file=sys.stderr,
        )
        return 1

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
