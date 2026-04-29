from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from klotto.core import sync_service
from klotto.core.sync_service import LottoSyncWorker


def _create_db(path: Path, draw_nos: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE draws (draw_no INTEGER PRIMARY KEY)")
        conn.executemany("INSERT INTO draws (draw_no) VALUES (?)", [(draw_no,) for draw_no in draw_nos])
        conn.commit()


def _record(draw_no: int) -> dict[str, object]:
    return {
        'draw_no': draw_no,
        'numbers': [1, 2, 3, 4, 5, 6],
        'bonus': 7,
        'date': f'2026-04-{draw_no:02d}',
        'first_prize': 1000000000,
        'first_winners': 10,
        'total_sales': 5000000000,
    }


def _run_worker(worker: LottoSyncWorker) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    worker.finished.connect(lambda payload: results.append(payload))
    worker.error.connect(lambda message: errors.append(message))
    worker.run()
    assert errors == []
    assert len(results) == 1
    return results[0]


def test_standard_sync_targets_recent_and_batched_historical(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db_path = tmp_path / 'lotto.db'
    _create_db(db_path, [1, 2, 3, 4, 5, 8, 9, 10, 11, 12])
    monkeypatch.setattr(sync_service, 'estimate_latest_draw', lambda: 15)

    worker = LottoSyncWorker(db_path, recent_window=3, mode='standard', historical_batch_size=1)
    monkeypatch.setattr(worker, '_fetch_draw', lambda draw_no: _record(draw_no))

    summary = _run_worker(worker)

    assert summary['attemptedDraws'] == [13, 14, 15, 6]
    assert summary['recentMissingCount'] == 3
    assert summary['historicalMissingCount'] == 2
    assert summary['status'] == 'success'


def test_full_repair_reports_warning_when_some_draws_fail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db_path = tmp_path / 'lotto.db'
    _create_db(db_path, [1, 3])
    monkeypatch.setattr(sync_service, 'estimate_latest_draw', lambda: 5)

    worker = LottoSyncWorker(db_path, recent_window=2, mode='full_repair', historical_batch_size=10)
    monkeypatch.setattr(worker, '_fetch_draw', lambda draw_no: None if draw_no == 4 else _record(draw_no))

    summary = _run_worker(worker)

    assert summary['attemptedDraws'] == [2, 4, 5]
    assert summary['failed_draws'] == [4]
    assert summary['status'] == 'warning'


def test_sync_worker_emits_cancelled_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db_path = tmp_path / 'lotto.db'
    _create_db(db_path, [1])
    monkeypatch.setattr(sync_service, 'estimate_latest_draw', lambda: 4)

    worker = LottoSyncWorker(db_path, recent_window=1, mode='standard', historical_batch_size=10)

    def _fetch_and_cancel(draw_no: int):
        worker.cancel()
        return _record(draw_no)

    monkeypatch.setattr(worker, '_fetch_draw', _fetch_and_cancel)

    summary = _run_worker(worker)

    assert summary['cancelled'] is True
    assert summary['status'] == 'cancelled'
    assert summary['fetched_records'][0]['draw_no'] == 2
