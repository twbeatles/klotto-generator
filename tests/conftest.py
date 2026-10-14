"""Session teardown: drain Qt work and pump the event loop before interpreter exit.

Some UI tests leave worker threads or a lingering QApplication behind. On
PySide6/shiboken that can corrupt the heap during interpreter teardown
(munmap_chunk / exit 134) after an otherwise green suite. This fixture joins
the global thread pool, pumps deferred deletes and runs a final GC pass.
Test-only; product code is untouched.
"""

import gc

import pytest


@pytest.fixture(scope="session", autouse=True)
def _qt_session_teardown():
    yield
    try:
        from PySide6.QtCore import QThreadPool
        from PySide6.QtWidgets import QApplication

        QThreadPool.globalInstance().waitForDone(15000)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.closeAllWindows()
            for window in app.topLevelWidgets():
                window.deleteLater()
            app.processEvents()
            app.processEvents()
    except Exception:
        pass
    gc.collect()
