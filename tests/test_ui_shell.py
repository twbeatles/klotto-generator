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
    generator_options: dict[str, Any] | None = None,
):
    store = _configure_app_paths(monkeypatch, tmp_path)
    if generator_options:
        store.state['generatorOptions'] = store.normalize_generator_options(generator_options)
        store.save()
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


def test_generation_input_conflict_warns_before_task(qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    app, _store, _fake_stats = _build_app(
        monkeypatch,
        tmp_path,
        [
            {'draw_no': 3, 'numbers': [1, 2, 3, 4, 5, 6], 'bonus': 7, 'date': '2026-04-01'},
            {'draw_no': 2, 'numbers': [7, 8, 9, 10, 11, 12], 'bonus': 13, 'date': '2026-03-25'},
            {'draw_no': 1, 'numbers': [14, 15, 16, 17, 18, 19], 'bonus': 20, 'date': '2026-03-18'},
        ],
        expected_latest_draw=3,
    )
    warnings: list[tuple[Any, ...]] = []
    monkeypatch.setattr(window_module.QMessageBox, 'warning', lambda *args, **_kwargs: warnings.append(args))
    try:
        app.generator_page.fixed_input.setPlainText('1')
        app.generator_page.exclude_input.setPlainText('1')

        app.generator_page.run_generation()

        assert warnings
        assert '겹칩니다' in str(warnings[0][2])
        assert app.generator_page._task is None
    finally:
        app.close()


def test_generator_options_restore_and_persist(qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    app, store, _fake_stats = _build_app(
        monkeypatch,
        tmp_path,
        [
            {'draw_no': 2, 'numbers': [1, 2, 3, 4, 5, 6], 'bonus': 7, 'date': '2026-04-01'},
            {'draw_no': 1, 'numbers': [7, 8, 9, 10, 11, 12], 'bonus': 13, 'date': '2026-03-25'},
        ],
        expected_latest_draw=2,
        generator_options={
            'num_sets': 7,
            'fixed_nums': '1, 2',
            'exclude_nums': '10-12',
            'check_consecutive': False,
            'consecutive_limit': 2,
        },
    )
    try:
        assert app.generator_page.set_count_spin.value() == 7
        assert app.generator_page.fixed_input.toPlainText() == '1, 2'
        assert app.generator_page.exclude_input.toPlainText() == '10-12'
        assert app.generator_page.strategy_editor.max_consecutive_spin.value() == -1

        app.generator_page.set_count_spin.setValue(6)
        app.generator_page.fixed_input.setPlainText('3')
        app.generator_page.exclude_input.setPlainText('20')
        app.generator_page._persist_generator_options({'filters': {'maxConsecutivePairs': 1}})

        assert store.state['generatorOptions'] == {
            'num_sets': 6,
            'fixed_nums': '3',
            'exclude_nums': '20',
            'check_consecutive': True,
            'consecutive_limit': 1,
        }
    finally:
        app.close()


def test_sync_meta_distinguishes_failure_partial_and_success(qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    app, store, _fake_stats = _build_app(
        monkeypatch,
        tmp_path,
        [
            {'draw_no': 3, 'numbers': [1, 2, 3, 4, 5, 6], 'bonus': 7, 'date': '2026-04-01'},
            {'draw_no': 2, 'numbers': [7, 8, 9, 10, 11, 12], 'bonus': 13, 'date': '2026-03-25'},
            {'draw_no': 1, 'numbers': [14, 15, 16, 17, 18, 19], 'bonus': 20, 'date': '2026-03-18'},
        ],
        expected_latest_draw=5,
    )
    try:
        store.state['syncMeta']['lastSuccessAt'] = 'old-success'
        store.state['syncMeta']['lastSuccessDrawNo'] = 3

        app._on_sync_finished({'target_count': 2, 'fetched_records': [], 'failed_draws': [4, 5], 'cancelled': False})
        assert store.state['syncMeta']['lastSuccessAt'] == 'old-success'
        assert store.state['syncMeta']['lastFailureAt']
        assert '4' in store.state['syncMeta']['lastFailureMessage']

        app._on_sync_finished({
            'target_count': 2,
            'fetched_records': [{'draw_no': 4, 'numbers': [3, 8, 13, 21, 34, 42], 'bonus': 1}],
            'failed_draws': [5],
            'cancelled': False,
        })
        assert store.state['syncMeta']['lastSuccessAt'] != 'old-success'
        assert store.state['syncMeta']['lastFailureAt'] == ''
        assert store.state['syncMeta']['lastWarningAt']
        assert '5' in store.state['syncMeta']['lastWarningMessage']

        app._on_sync_finished({
            'target_count': 1,
            'fetched_records': [{'draw_no': 5, 'numbers': [4, 9, 14, 19, 24, 29], 'bonus': 2}],
            'failed_draws': [],
            'cancelled': False,
        })
        assert store.state['syncMeta']['lastFailureAt'] == ''
        assert store.state['syncMeta']['lastWarningAt'] == ''
        assert store.state['syncMeta']['lastSuccessDrawNo'] == 5
    finally:
        app.close()


def test_qr_scan_and_excel_buttons_call_connected_flows(qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db_path = tmp_path / 'lotto_history.db'
    db_path.write_bytes(b'placeholder')
    monkeypatch.setitem(APP_CONFIG, 'LOTTO_HISTORY_DB', db_path)
    app, _store, _fake_stats = _build_app(
        monkeypatch,
        tmp_path,
        [{'draw_no': 1, 'numbers': [1, 2, 3, 4, 5, 6], 'bonus': 7, 'date': '2026-04-01'}],
        expected_latest_draw=1,
    )
    qr_payloads: list[Any] = []
    excel_paths: list[Path] = []

    class FakeScanner:
        def __init__(self, *_args, **_kwargs):
            self.scanned_data = {'draw_no': 1, 'sets': [[1, 2, 3, 4, 5, 6]]}

        def exec(self):
            return window_module.QDialog.DialogCode.Accepted

    class FakeWinningCheckDialog:
        def __init__(self, *_args, qr_payload=None, **_kwargs):
            qr_payloads.append(qr_payload)

        def exec(self):
            return None

    monkeypatch.setattr(window_module, 'QRCodeScannerDialog', FakeScanner)
    monkeypatch.setattr(window_module, 'WinningCheckDialog', FakeWinningCheckDialog)

    import scripts.export_to_excel as excel_module
    monkeypatch.setattr(excel_module, 'ensure_openpyxl', lambda: True)
    monkeypatch.setattr(excel_module, 'export_to_excel', lambda path: excel_paths.append(Path(path)) or True)
    monkeypatch.setattr(window_module.QFileDialog, 'getSaveFileName', lambda *_args, **_kwargs: (str(tmp_path / 'out.xlsx'), ''))
    try:
        app.check_page.open_qr_scanner()
        app.data_page.export_winning_excel()

        assert qr_payloads == [{'draw_no': 1, 'sets': [[1, 2, 3, 4, 5, 6]]}]
        assert excel_paths == [tmp_path / 'out.xlsx']
    finally:
        app.close()


def test_backtest_strategy_list_refreshes_when_experimental_toggle_changes(qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    app, _store, _fake_stats = _build_app(
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
        initial_count = app.backtest_page.strategy_list.count()
        app.backtest_page.strategy_editor.experimental_chk.setChecked(True)

        ids = []
        for index in range(app.backtest_page.strategy_list.count()):
            item = app.backtest_page.strategy_list.item(index)
            assert item is not None
            ids.append(item.data(window_module.Qt.ItemDataRole.UserRole))
        assert app.backtest_page.strategy_list.count() > initial_count
        assert 'skip_hit_weighted' in ids
    finally:
        app.close()
