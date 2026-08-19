from __future__ import annotations

from typing import Any, Callable, Optional

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QWidget

from klotto.logging import logger


class TaskThread(QThread):
    resultReady = pyqtSignal(object)
    errorOccurred = pyqtSignal(str)

    def __init__(self, fn: Callable[[], Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            result = self.fn()
            self.resultReady.emit(result)
        except Exception as exc:  # pragma: no cover - surfaced to UI
            logger.exception('Background task failed')
            self.errorOccurred.emit(str(exc))


