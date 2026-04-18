from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from klotto.core import sync_service
from klotto.core.sync_service import LottoSyncWorker
from klotto.net import client as client_module


def _api_payload(draw_no: int) -> str:
    return json.dumps(
        {
            'data': {
                'list': [
                    {
                        'ltEpsd': draw_no,
                        'ltRflYmd': '20260418',
                        'tm1WnNo': 1,
                        'tm2WnNo': 2,
                        'tm3WnNo': 3,
                        'tm4WnNo': 4,
                        'tm5WnNo': 5,
                        'tm6WnNo': 6,
                        'bnsWnNo': 7,
                        'rnk1WnAmt': 1000000000,
                        'rnk1WnNope': 10,
                        'rlvtEpsdSumNtslAmt': 5000000000,
                    }
                ]
            }
        }
    )


def test_sync_worker_uses_proxy_aware_fetch_helper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    calls: list[tuple[int, str]] = []
    results: list[dict[str, Any]] = []

    monkeypatch.setattr(sync_service, 'estimate_latest_draw', lambda: 1)
    monkeypatch.setattr(
        sync_service,
        'fetch_lotto_api_text',
        lambda draw_no, proxy_url='': calls.append((draw_no, proxy_url)) or _api_payload(draw_no),
    )

    worker = LottoSyncWorker(tmp_path / 'lotto.db', proxy_url='http://localhost:8080')
    worker.finished.connect(lambda payload: results.append(payload))
    worker.run()

    assert calls == [(1, 'http://localhost:8080')]
    assert results[0]['fetched_records'][0]['draw_no'] == 1


def test_lotto_api_worker_uses_same_proxy_aware_helper(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[int, str]] = []
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    monkeypatch.setattr(
        client_module,
        'fetch_lotto_api_text',
        lambda draw_no, proxy_url='': calls.append((draw_no, proxy_url)) or _api_payload(draw_no),
    )

    worker = client_module.LottoApiWorker([7], proxy_url='http://localhost:9999')
    worker.finished.connect(lambda payload: results.append(payload))
    worker.error.connect(lambda message: errors.append(message))
    worker.run()

    assert errors == []
    assert calls == [(7, 'http://localhost:9999')]
    assert results[0]['drwNo'] == 7
