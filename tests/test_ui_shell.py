from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget

from klotto.config import APP_CONFIG
from klotto.data.app_state import AppStateStore
from klotto.ui.main_window import window as window_module


class StubWinningInfoWidget(QWidget):
    dataLoaded = pyqtSignal(dict)

    def __init__(self, *args, **kwargs):
        super().__init__()


class FakeStatsManager:
    def __init__(self, winning_data: list[dict[str, Any]]):
        self.winning_data = [dict(item) for item in winning_data]

    def get_frequency_analysis(self) -> dict[str, list[tuple[int, int]]]:
        counts = {number: 0 for number in range(1, 46)}
        for draw in self.winning_data:
            for number in draw.get('numbers', []):
                counts[int(number)] += 1
        ordered = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
        return {
            'most_common': ordered[:10],
            'least_common': list(reversed(ordered[-10:])),
        }

    def upsert_winning_data(self, draw_no: int, numbers: list[int], bonus: int, **kwargs):
        record = {'draw_no': draw_no, 'numbers': list(numbers), 'bonus': bonus, **kwargs}
        for index, existing in enumerate(self.winning_data):
            if int(existing.get('draw_no', 0)) == int(draw_no):
                self.winning_data[index] = record
                return 'updated'
        self.winning_data.append(record)
        self.winning_data.sort(key=lambda item: int(item.get('draw_no', 0)), reverse=True)
        return 'inserted'


def _configure_app_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AppStateStore:
    state_dir = tmp_path / 'state'
    monkeypatch.setitem(APP_CONFIG, 'FAVORITES_FILE', state_dir / 'favorites.json')
    monkeypatch.setitem(APP_CONFIG, 'HISTORY_FILE', state_dir / 'history.json')
    monkeypatch.setitem(APP_CONFIG, 'SETTINGS_FILE', state_dir / 'settings.json')
    monkeypatch.setitem(APP_CONFIG, 'APP_STATE_FILE', state_dir / 'app_state.json')
    return AppStateStore(state_dir / 'app_state.json')


@pytest.fixture(scope='module')
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    return app


def _build_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    winning_data: list[dict[str, Any]],
    *,
    expected_latest_draw: int,
):
    store = _configure_app_paths(monkeypatch, tmp_path)
    fake_stats = FakeStatsManager(winning_data)
    monkeypatch.setattr(window_module, 'get_shared_store', lambda: store)
    monkeypatch.setattr(window_module, 'WinningStatsManager', lambda: fake_stats)
    monkeypatch.setattr(window_module, 'WinningInfoWidget', StubWinningInfoWidget)
    monkeypatch.setattr(window_module, 'estimate_latest_draw', lambda: expected_latest_draw)
    app = window_module.LottoApp()
    return app, store, fake_stats


def test_navigation_and_data_health_gate(qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    app, store, fake_stats = _build_app(
        monkeypatch,
        tmp_path,
        [
            {'draw_no': 3, 'numbers': [1, 2, 3, 4, 5, 6], 'bonus': 7, 'date': '2026-04-01'},
            {'draw_no': 1, 'numbers': [7, 8, 9, 10, 11, 12], 'bonus': 13, 'date': '2026-03-18'},
        ],
        expected_latest_draw=4,
    )
    try:
        assert app.nav_list.count() == 7
        app.nav_list.setCurrentRow(3)
        assert app.stack.currentIndex() == 3

        assert store.state['dataHealth']['availability'] == 'partial'
        assert not app.ai_page.generate_btn.isEnabled()
        assert not app.backtest_page.run_btn.isEnabled()

        fake_stats.winning_data = [
            {'draw_no': 3, 'numbers': [1, 2, 3, 4, 5, 6], 'bonus': 7, 'date': '2026-04-01'},
            {'draw_no': 2, 'numbers': [7, 8, 9, 10, 11, 12], 'bonus': 13, 'date': '2026-03-25'},
            {'draw_no': 1, 'numbers': [14, 15, 16, 17, 18, 19], 'bonus': 20, 'date': '2026-03-18'},
        ]
        app.refresh_all_views()

        assert store.state['dataHealth']['availability'] == 'full'
        assert app.ai_page.generate_btn.isEnabled()
        assert app.backtest_page.run_btn.isEnabled()
    finally:
        app.close()


def test_data_page_remove_and_clear_actions(qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    app, store, _fake_stats = _build_app(
        monkeypatch,
        tmp_path,
        [
            {'draw_no': 3, 'numbers': [1, 2, 3, 4, 5, 6], 'bonus': 7, 'date': '2026-04-01'},
            {'draw_no': 2, 'numbers': [7, 8, 9, 10, 11, 12], 'bonus': 13, 'date': '2026-03-25'},
            {'draw_no': 1, 'numbers': [14, 15, 16, 17, 18, 19], 'bonus': 20, 'date': '2026-03-18'},
        ],
        expected_latest_draw=3,
    )
    try:
        store.add_favorite([1, 2, 3, 4, 5, 6], memo='fav')
        store.add_history_entry([7, 8, 9, 10, 11, 12], created_at='2026-04-15T10:00:00')
        store.add_tickets_bulk(
            [
                {
                    'id': 'ticket-1',
                    'numbers': [3, 8, 13, 21, 34, 42],
                    'targetDrawNo': 3,
                    'source': 'generator',
                    'campaignId': 'campaign-1',
                    'quantity': 1,
                }
            ],
            winning_data=app.stats_manager.winning_data,
        )
        store.add_campaign(
            {
                'id': 'campaign-1',
                'name': 'April campaign',
                'startDrawNo': 3,
                'weeks': 1,
                'setsPerWeek': 1,
            }
        )
        app.refresh_all_views()

        app.data_page.tabs.setCurrentIndex(0)
        app.data_page.tables['favorites'].selectRow(0)
        app.data_page.remove_selected()
        assert store.state['favorites'] == []

        app.data_page.tabs.setCurrentIndex(2)
        app.data_page.clear_current_tab()
        assert store.state['ticketBook'] == []
        assert store.state['campaigns'] == []
    finally:
        app.close()
