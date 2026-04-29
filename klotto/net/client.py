from __future__ import annotations

import json
import urllib.error
from typing import Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from klotto.core.draws import convert_new_api_response
from klotto.logging import logger
from klotto.net.http import fetch_lotto_api_text


class LottoApiWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, draw_nos: list[int], *, proxy_url: str = ""):
        super().__init__()
        self.draw_nos = draw_nos
        self.proxy_url = str(proxy_url or "")
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        for index, draw_no in enumerate(self.draw_nos):
            if self._is_cancelled:
                return

            if index > 0:
                self.msleep(200)

            try:
                logger.info("Requesting draw #%s from lotto API", draw_no)
                raw_data = fetch_lotto_api_text(draw_no, proxy_url=self.proxy_url)
                if self._is_cancelled:
                    return

                if not raw_data.strip().startswith("{"):
                    logger.error("Response is not JSON. First 200 chars: %s", raw_data[:200])
                    self.error.emit(f"{draw_no}회차: 서버 응답 오류")
                    continue

                payload = json.loads(raw_data)
                converted = convert_new_api_response(payload)
                if converted and converted.get("drwNo"):
                    logger.info("Successfully fetched draw #%s", draw_no)
                    self.finished.emit(converted)
                else:
                    self.error.emit(f"{draw_no}회차 정보를 찾을 수 없습니다.")
            except urllib.error.URLError as exc:
                logger.error("Network error for #%s: %s", draw_no, exc)
                self.error.emit(f"{draw_no}회차: 네트워크 오류")
            except json.JSONDecodeError as exc:
                logger.error("JSON parse error for #%s: %s", draw_no, exc)
                self.error.emit(f"{draw_no}회차: 데이터 파싱 오류")
            except Exception as exc:
                logger.error("Unknown error for #%s: %s", draw_no, exc)
                self.error.emit(f"{draw_no}회차: 알 수 없는 오류")


class LottoNetworkManager(QObject):
    dataLoaded = pyqtSignal(dict)
    errorOccurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_worker: Optional[LottoApiWorker] = None

    def _disconnect_worker_signals(self, worker: LottoApiWorker):
        try:
            worker.finished.disconnect(self.dataLoaded.emit)
        except (TypeError, RuntimeError):
            pass

        try:
            worker.error.disconnect(self.errorOccurred.emit)
        except (TypeError, RuntimeError):
            pass

    def fetch_draw(self, draw_no: int, *, proxy_url: str = ""):
        self.fetch_draws([draw_no], proxy_url=proxy_url)

    def fetch_draws(self, draw_nos: list[int], *, proxy_url: str = ""):
        if self._current_worker and self._current_worker.isRunning():
            self._disconnect_worker_signals(self._current_worker)
            self._current_worker.cancel()
        elif self._current_worker:
            self._disconnect_worker_signals(self._current_worker)

        self._current_worker = LottoApiWorker(draw_nos, proxy_url=proxy_url)
        self._current_worker.finished.connect(self.dataLoaded.emit)
        self._current_worker.error.connect(self.errorOccurred.emit)
        self._current_worker.start()

    def cancel(self):
        if not self._current_worker:
            return

        self._disconnect_worker_signals(self._current_worker)
        if self._current_worker.isRunning():
            self._current_worker.cancel()
        self._current_worker = None
