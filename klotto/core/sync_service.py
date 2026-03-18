"""
로또 당첨 정보 백그라운드 동기화 서비스
앱 시작 시 최신 당첨 정보를 DB에 자동 업데이트
"""

import json
import sqlite3
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from PyQt6.QtCore import QThread, pyqtSignal

from klotto.config import APP_CONFIG
from klotto.core.draws import convert_new_api_response, estimate_latest_draw, normalize_legacy_draw_payload
from klotto.logging import logger


class LottoSyncWorker(QThread):
    """백그라운드에서 최신 당첨 정보를 동기화하는 워커"""

    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, db_path: Path, recent_window: int = 20):
        super().__init__()
        self.db_path = db_path
        self.recent_window = recent_window
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def _get_last_draw_no(self) -> int:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(draw_no) FROM draws")
                result = cursor.fetchone()
            return result[0] if result and result[0] else 0
        except sqlite3.OperationalError:
            return 0
        except Exception as exc:
            logger.error("Failed to read last draw number: %s", exc)
            return 0

    def _get_existing_draws(self, start_draw: int, end_draw: int) -> set[int]:
        if start_draw > end_draw:
            return set()

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT draw_no
                    FROM draws
                    WHERE draw_no BETWEEN ? AND ?
                    """,
                    (start_draw, end_draw),
                )
                rows = cursor.fetchall()
            return {int(row[0]) for row in rows if row and row[0]}
        except sqlite3.OperationalError:
            return set()
        except Exception as exc:
            logger.error("Failed to read existing draws: %s", exc)
            return set()

    def _get_sync_targets(self, current_draw: int) -> List[int]:
        last_draw = self._get_last_draw_no()
        repair_start = max(1, current_draw - self.recent_window)
        recent_existing = self._get_existing_draws(repair_start, current_draw)

        repair_targets = [draw_no for draw_no in range(repair_start, current_draw + 1) if draw_no not in recent_existing]
        repair_set = set(repair_targets)
        new_targets = [draw_no for draw_no in range(last_draw + 1, current_draw + 1) if draw_no not in repair_set]

        return repair_targets + new_targets

    def _fetch_draw(self, draw_no: int) -> Optional[Dict[str, Any]]:
        try:
            url = f"https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do?srchLtEpsd={draw_no}"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://www.dhlottery.co.kr/lt645/result",
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                data = response.read().decode("utf-8")
                result = json.loads(data)

            legacy_payload = convert_new_api_response(result)
            normalized = normalize_legacy_draw_payload(legacy_payload or {})
            if normalized:
                return normalized
            return None
        except Exception as exc:
            logger.error("Fetch error for draw %s: %s", draw_no, exc)
            return None

    def run(self):
        if not self.db_path:
            self.error.emit("DB 경로가 설정되지 않았습니다.")
            return

        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        current_draw = estimate_latest_draw()
        targets = self._get_sync_targets(current_draw)
        if not targets:
            logger.info("DB is up to date (latest: %s)", current_draw)
            self.finished.emit(
                {
                    "target_count": 0,
                    "fetched_records": [],
                    "failed_draws": [],
                    "cancelled": False,
                }
            )
            return

        fetched_records: List[Dict[str, Any]] = []
        failed_draws: List[int] = []

        for draw_no in targets:
            if self._is_cancelled:
                self.finished.emit(
                    {
                        "target_count": len(targets),
                        "fetched_records": fetched_records,
                        "failed_draws": failed_draws,
                        "cancelled": True,
                    }
                )
                return

            record = self._fetch_draw(draw_no)
            if record:
                fetched_records.append(record)
                logger.info("Fetched draw #%s for sync", draw_no)
            else:
                failed_draws.append(draw_no)

            self.msleep(200)

        self.finished.emit(
            {
                "target_count": len(targets),
                "fetched_records": fetched_records,
                "failed_draws": failed_draws,
                "cancelled": False,
            }
        )


def start_background_sync(stats_manager=None) -> Optional[LottoSyncWorker]:
    """백그라운드 동기화 시작 (호출자가 워커 참조 유지 필요)"""

    db_path = cast(Path, APP_CONFIG.get("LOTTO_HISTORY_DB"))
    if not db_path:
        return None

    worker = LottoSyncWorker(db_path, recent_window=20)

    def on_finished(summary: Dict[str, Any]):
        fetched_records = summary.get("fetched_records", [])
        failed_draws = summary.get("failed_draws", [])
        cancelled = bool(summary.get("cancelled", False))

        inserted_count = 0
        updated_count = 0
        unchanged_count = 0
        invalid_count = 0

        if stats_manager:
            for record in fetched_records:
                status = stats_manager.upsert_winning_data(
                    record["draw_no"],
                    record["numbers"],
                    record["bonus"],
                    draw_date=record.get("date"),
                    first_prize=record.get("first_prize"),
                    first_winners=record.get("first_winners"),
                    total_sales=record.get("total_sales"),
                )
                if status == "inserted":
                    inserted_count += 1
                elif status == "updated":
                    updated_count += 1
                elif status == "unchanged":
                    unchanged_count += 1
                else:
                    invalid_count += 1
        else:
            inserted_count = len(fetched_records)

        if inserted_count or updated_count or unchanged_count or invalid_count:
            logger.info(
                "Background sync completed: inserted=%s updated=%s unchanged=%s invalid=%s",
                inserted_count,
                updated_count,
                unchanged_count,
                invalid_count,
            )
        else:
            logger.info("Background sync completed with no changes")

        if failed_draws:
            logger.warning("Background sync failed draws: %s", ", ".join(str(draw) for draw in failed_draws))

        if cancelled:
            logger.info("Background sync cancelled")

    worker.finished.connect(on_finished)
    worker.start()
    return worker
