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
from klotto.ui.widgets import strategy_editor as strategy_editor_module


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

    def get_draw_data(self, draw_no: int):
        for item in self.winning_data:
            if int(item.get('draw_no', 0)) == int(draw_no):
                return dict(item)
        return None


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


def test_refresh_all_views_preserves_form_state(qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
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
        app.generator_page.set_count_spin.setValue(9)
        app.generator_page.fixed_input.setPlainText('1, 2')
        app.generator_page.exclude_input.setPlainText('3, 4')
        app.ai_page.set_count_spin.setValue(7)
        app.ai_page.fixed_input.setPlainText('5, 6')
        app.backtest_page.start_draw_spin.setValue(1)
        app.backtest_page.end_draw_spin.setValue(2)
        app.backtest_page.qty_spin.setValue(4)
        selected_before = set()
        if app.backtest_page.strategy_list.count() > 0:
            first_item = app.backtest_page.strategy_list.item(0)
            assert first_item is not None
            first_item.setSelected(True)
            selected_before.add(str(first_item.data(window_module.Qt.ItemDataRole.UserRole)))
        if app.backtest_page.strategy_list.count() > 1:
            second_item = app.backtest_page.strategy_list.item(1)
            assert second_item is not None
            second_item.setSelected(True)
            selected_before.add(str(second_item.data(window_module.Qt.ItemDataRole.UserRole)))

        app.refresh_all_views()

        assert app.generator_page.set_count_spin.value() == 9
        assert app.generator_page.fixed_input.toPlainText() == '1, 2'
        assert app.generator_page.exclude_input.toPlainText() == '3, 4'
        assert app.ai_page.set_count_spin.value() == 7
        assert app.ai_page.fixed_input.toPlainText() == '5, 6'
        assert app.backtest_page.start_draw_spin.value() == 1
        assert app.backtest_page.end_draw_spin.value() == 2
        assert app.backtest_page.qty_spin.value() == 4
        assert store.state['generatorOptions']['num_sets'] == 9
        assert store.state['generatorOptions']['fixed_nums'] == '1, 2'
        assert store.state['generatorOptions']['exclude_nums'] == '3, 4'
        assert {
            str(item.data(window_module.Qt.ItemDataRole.UserRole))
            for item in app.backtest_page.strategy_list.selectedItems()
        } == selected_before
    finally:
        app.close()


def test_settings_page_saves_proxy_and_alert_preferences(qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
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
        app.settings_page.proxy_input.setText('not-a-proxy')
        app.settings_page._save_proxy()
        assert store.state['proxyUrl'] == ''

        app.settings_page.proxy_input.setText('http://localhost:8080')
        app.settings_page._save_proxy()
        assert store.state['proxyUrl'] == 'http://localhost:8080'

        app.settings_page.enable_in_app_chk.setChecked(False)
        app.settings_page.notify_new_result_chk.setChecked(False)
        assert store.state['alertPrefs']['enableInApp'] is False
        assert store.state['alertPrefs']['notifyOnNewResult'] is False
    finally:
        app.close()


def test_sync_finish_settles_existing_tickets_and_updates_success_meta(qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    app, store, _fake_stats = _build_app(
        monkeypatch,
        tmp_path,
        [
            {'draw_no': 3, 'numbers': [7, 8, 9, 10, 11, 12], 'bonus': 13, 'date': '2026-04-01'},
            {'draw_no': 2, 'numbers': [14, 15, 16, 17, 18, 19], 'bonus': 20, 'date': '2026-03-25'},
            {'draw_no': 1, 'numbers': [21, 22, 23, 24, 25, 26], 'bonus': 27, 'date': '2026-03-18'},
        ],
        expected_latest_draw=4,
    )
    try:
        store.add_tickets_bulk(
            [
                {
                    'numbers': [1, 2, 3, 4, 5, 6],
                    'targetDrawNo': 4,
                    'source': 'generator',
                    'quantity': 1,
                }
            ],
            winning_data=app.stats_manager.winning_data,
        )
        assert store.state['ticketBook'][0]['checked'] is None

        app._sync_start_latest_draw = 3
        app._on_sync_finished(
            {
                'mode': 'standard',
                'fetched_records': [
                    {
                        'draw_no': 4,
                        'numbers': [1, 2, 3, 4, 5, 6],
                        'bonus': 7,
                        'date': '2026-04-08',
                        'first_prize': 1000000000,
                        'first_winners': 10,
                        'total_sales': 5000000000,
                    }
                ],
                'failed_draws': [],
                'recentMissingCount': 1,
                'historicalMissingCount': 0,
                'cancelled': False,
            }
        )

        assert store.state['ticketBook'][0]['checked']['rank'] == 1
        assert store.state['syncMeta']['mode'] == 'standard'
        assert store.state['syncMeta']['lastSuccessDrawNo'] == 4
        assert '새 최신 회차 4회 결과를 반영했습니다.' in app.settings_page.log.toPlainText()
        assert store.state['dataHealth']['availability'] == 'full'
    finally:
        app.close()


def test_sync_warning_updates_warning_meta_without_touching_last_success(qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    app, store, _fake_stats = _build_app(
        monkeypatch,
        tmp_path,
        [
            {'draw_no': 3, 'numbers': [7, 8, 9, 10, 11, 12], 'bonus': 13, 'date': '2026-04-01'},
            {'draw_no': 2, 'numbers': [14, 15, 16, 17, 18, 19], 'bonus': 20, 'date': '2026-03-25'},
            {'draw_no': 1, 'numbers': [21, 22, 23, 24, 25, 26], 'bonus': 27, 'date': '2026-03-18'},
        ],
        expected_latest_draw=4,
    )
    try:
        store.state['syncMeta']['lastSuccessAt'] = ''
        store.state['syncMeta']['lastSuccessDrawNo'] = 0
        app._on_sync_finished(
            {
                'mode': 'standard',
                'fetched_records': [
                    {
                        'draw_no': 4,
                        'numbers': [1, 2, 3, 4, 5, 6],
                        'bonus': 7,
                        'date': '2026-04-08',
                        'first_prize': 1000000000,
                        'first_winners': 10,
                        'total_sales': 5000000000,
                    }
                ],
                'failed_draws': [5],
                'recentMissingCount': 1,
                'historicalMissingCount': 0,
                'cancelled': False,
            }
        )

        assert store.state['syncMeta']['lastSuccessAt'] == ''
        assert store.state['syncMeta']['lastSuccessDrawNo'] == 0
        assert store.state['syncMeta']['lastWarningAt'] != ''
        assert '5' in store.state['syncMeta']['lastWarningMessage']
    finally:
        app.close()


def test_strategy_presets_can_be_saved_loaded_and_deleted(qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
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
        editor = app.generator_page.strategy_editor
        editor.lookback_spin.setValue(33)
        monkeypatch.setattr(strategy_editor_module.QInputDialog, 'getText', lambda *args, **kwargs: ('테스트 프리셋', True))
        editor.save_current_preset()

        presets = store.get_strategy_presets('generator')
        assert len(presets) == 1
        assert presets[0]['name'] == '테스트 프리셋'

        editor.lookback_spin.setValue(44)
        preset_index = editor.preset_combo.findData(presets[0]['id'])
        editor.preset_combo.setCurrentIndex(preset_index)
        editor.load_selected_preset()
        assert editor.lookback_spin.value() == 33

        monkeypatch.setattr(
            strategy_editor_module.QMessageBox,
            'question',
            lambda *args, **kwargs: strategy_editor_module.QMessageBox.StandardButton.Yes,
        )
        editor.delete_selected_preset()
        assert store.get_strategy_presets('generator') == []
    finally:
        app.close()
