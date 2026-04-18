from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from PyQt6.QtCore import QThread, pyqtSignal

from klotto.config import APP_CONFIG
from klotto.core.draws import (
    convert_new_api_response,
    estimate_latest_draw,
    normalize_legacy_draw_payload,
    split_missing_draws,
)
from klotto.logging import logger
from klotto.net.http import fetch_lotto_api_text


class LottoSyncWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(
        self,
        db_path: Path,
        *,
        recent_window: int = 20,
        proxy_url: str = "",
        mode: str = "standard",
        historical_batch_size: int = 10,
    ):
        super().__init__()
        self.db_path = db_path
        self.recent_window = max(0, int(recent_window))
        self.proxy_url = str(proxy_url or "")
        self.mode = "full_repair" if str(mode) == "full_repair" else "standard"
        self.historical_batch_size = max(0, int(historical_batch_size))
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def _get_existing_draws(self) -> set[int]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT draw_no FROM draws")
                rows = cursor.fetchall()
            return {int(row[0]) for row in rows if row and row[0]}
        except sqlite3.OperationalError:
            return set()
        except Exception as exc:
            logger.error("Failed to read existing draws: %s", exc)
            return set()

    def _get_sync_targets(self, current_draw: int) -> Dict[str, Any]:
        existing = self._get_existing_draws()
        latest_existing = max(existing) if existing else 0
        allowed_missing = set(APP_CONFIG["ALLOWED_MISSING_DRAWS"])
        missing = split_missing_draws(
            existing,
            current_draw,
            current_draw=current_draw,
            recent_window=self.recent_window,
            allowed_missing=allowed_missing,
        )

        if self.mode == "full_repair":
            targets = list(missing["all"])
        else:
            new_targets = [
                draw_no
                for draw_no in range(latest_existing + 1, current_draw + 1)
                if draw_no not in allowed_missing
            ]
            historical_batch = missing["historical"][: self.historical_batch_size]
            ordered_targets: List[int] = []
            seen: set[int] = set()
            for draw_no in [*new_targets, *missing["recent"], *historical_batch]:
                if draw_no > 0 and draw_no not in seen:
                    seen.add(draw_no)
                    ordered_targets.append(draw_no)
            targets = ordered_targets

        return {
            "targets": targets,
            "latest_existing": latest_existing,
            "recent_missing": list(missing["recent"]),
            "historical_missing": list(missing["historical"]),
        }

    def _fetch_draw(self, draw_no: int) -> Optional[Dict[str, Any]]:
        try:
            raw_data = fetch_lotto_api_text(draw_no, proxy_url=self.proxy_url)
            payload = json.loads(raw_data)
            legacy_payload = convert_new_api_response(payload)
            normalized = normalize_legacy_draw_payload(legacy_payload or {})
            if normalized:
                return normalized
            return None
        except Exception as exc:
            logger.error("Fetch error for draw %s: %s", draw_no, exc)
            return None

    def _build_summary(
        self,
        *,
        targets: List[int],
        fetched_records: List[Dict[str, Any]],
        failed_draws: List[int],
        cancelled: bool,
        recent_missing_count: int,
        historical_missing_count: int,
    ) -> Dict[str, Any]:
        if cancelled:
            status = "cancelled"
        elif failed_draws and not fetched_records:
            status = "failure"
        elif failed_draws:
            status = "warning"
        else:
            status = "success"
        return {
            "status": status,
            "mode": self.mode,
            "target_count": len(targets),
            "attemptedDraws": list(targets),
            "fetched_records": list(fetched_records),
            "failed_draws": list(failed_draws),
            "recentMissingCount": int(recent_missing_count),
            "historicalMissingCount": int(historical_missing_count),
            "settledTickets": 0,
            "cancelled": cancelled,
        }

    def run(self):
        if not self.db_path:
            self.error.emit("DB 경로가 설정되지 않았습니다.")
            return

        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        current_draw = estimate_latest_draw()
        plan = self._get_sync_targets(current_draw)
        targets = list(plan["targets"])
        recent_missing_count = len(plan["recent_missing"])
        historical_missing_count = len(plan["historical_missing"])

        if not targets:
            logger.info("DB is up to date (latest: %s, mode=%s)", current_draw, self.mode)
            self.finished.emit(
                self._build_summary(
                    targets=[],
                    fetched_records=[],
                    failed_draws=[],
                    cancelled=False,
                    recent_missing_count=recent_missing_count,
                    historical_missing_count=historical_missing_count,
                )
            )
            return

        fetched_records: List[Dict[str, Any]] = []
        failed_draws: List[int] = []

        for draw_no in targets:
            if self._is_cancelled:
                self.finished.emit(
                    self._build_summary(
                        targets=targets,
                        fetched_records=fetched_records,
                        failed_draws=failed_draws,
                        cancelled=True,
                        recent_missing_count=recent_missing_count,
                        historical_missing_count=historical_missing_count,
                    )
                )
                return

            record = self._fetch_draw(draw_no)
            if record:
                fetched_records.append(record)
                logger.info("Fetched draw #%s for sync (%s)", draw_no, self.mode)
            else:
                failed_draws.append(draw_no)

            self.msleep(200)

        self.finished.emit(
            self._build_summary(
                targets=targets,
                fetched_records=fetched_records,
                failed_draws=failed_draws,
                cancelled=False,
                recent_missing_count=recent_missing_count,
                historical_missing_count=historical_missing_count,
            )
        )


def start_background_sync(stats_manager=None) -> Optional[LottoSyncWorker]:
    db_path = cast(Path, APP_CONFIG.get("LOTTO_HISTORY_DB"))
    if not db_path:
        return None

    worker = LottoSyncWorker(
        db_path,
        recent_window=int(APP_CONFIG["SYNC_RECENT_WINDOW"]),
        proxy_url="",
        mode="standard",
        historical_batch_size=int(APP_CONFIG["HISTORICAL_SYNC_BATCH_SIZE"]),
    )

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

        logger.info(
            "Background sync finished: status=%s inserted=%s updated=%s unchanged=%s invalid=%s failed=%s cancelled=%s",
            summary.get("status"),
            inserted_count,
            updated_count,
            unchanged_count,
            invalid_count,
            len(failed_draws),
            cancelled,
        )

    worker.finished.connect(on_finished)
    worker.start()
    return worker
