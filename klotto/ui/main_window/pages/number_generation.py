from __future__ import annotations


import datetime as dt
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, TYPE_CHECKING

from PyQt6.QtCore import QByteArray, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from klotto.config import APP_CONFIG
from klotto.core.backtest import run_backtest
from klotto.core.draws import estimate_latest_draw, split_missing_draws
from klotto.core.lotto_rules import parse_number_expression, validate_generation_constraints
from klotto.core.pension720_engine import Pension720Engine
from klotto.core.pension720_strategy_catalog import (
    get_pension720_strategy_meta,
    list_pension720_strategies,
    resolve_pension720_strategy_id,
)
from klotto.core.stats import WinningStatsManager
from klotto.core.sync_service import LottoSyncWorker
from klotto.core.strategy_engine import StrategyEngine
from klotto.data.pension720 import (
    build_pension720_ticket_csv,
    fetch_pension720_official_stats,
    load_pension720_static_data,
    resolve_pension720_ticket_check,
)
from klotto.data.app_state import get_shared_store
from klotto.data.exporter import DataExporter
from klotto.data.favorites import FavoritesManager
from klotto.data.history import HistoryManager
from klotto.logging import logger
from klotto.net.http import normalize_proxy_url
from klotto.ui.dialogs import ExportImportDialog, WinningCheckDialog
from klotto.ui.scanner import QRCodeScannerDialog
from klotto.ui.theme import ThemeManager
from klotto.ui.widgets import StrategyRequestEditor, WinningInfoWidget



from klotto.ui.main_window.task_thread import TaskThread

if TYPE_CHECKING:
    from klotto.ui.main_window.window import LottoApp

class NumberGenerationPage(QWidget):
    def __init__(self, app_window: 'LottoApp', scope: str, title: str, *, enable_campaign: bool = False):
        super().__init__(app_window)
        self.app_window = app_window
        self.scope = scope
        self.enable_campaign = enable_campaign
        self.generated_rows: List[Dict[str, Any]] = []
        self._task: Optional[TaskThread] = None
        self._is_hydrating = False
        self._setup_ui(title)
        self.hydrate_defaults()

    def _setup_ui(self, title: str):
        layout = QVBoxLayout(self)
        if self.scope == 'generator':
            self.winning_info_widget = WinningInfoWidget(
                self.app_window.stats_manager,
                proxy_url_getter=lambda: str(self.app_window.store.state.get('proxyUrl') or ''),
            )
            self.winning_info_widget.dataLoaded.connect(lambda _payload: self.app_window.refresh_all_views())
            layout.addWidget(self.winning_info_widget)

        header = QLabel(title)
        header.setFont(QFont('Segoe UI', 16, QFont.Weight.Bold))
        layout.addWidget(header)

        top = QHBoxLayout()
        self.strategy_editor = StrategyRequestEditor(self.scope, '전략 / 필터', store=self.app_window.store)
        self.strategy_editor.presetApplied.connect(self._on_preset_applied)
        top.addWidget(self.strategy_editor, 2)

        side = QGroupBox('실행 옵션')
        side_form = QFormLayout(side)
        self.set_count_spin = QSpinBox()
        self.set_count_spin.setRange(1, APP_CONFIG['MAX_SETS'])
        self.set_count_spin.setValue(5)
        side_form.addRow('세트 수', self.set_count_spin)

        self.fixed_input = QTextEdit()
        self.fixed_input.setPlaceholderText('예: 1, 3, 5-8')
        self.fixed_input.setFixedHeight(56)
        side_form.addRow('고정수', self.fixed_input)

        self.exclude_input = QTextEdit()
        self.exclude_input.setPlaceholderText('예: 7-10, 22')
        self.exclude_input.setFixedHeight(56)
        side_form.addRow('제외수', self.exclude_input)

        self.target_draw_spin = QSpinBox()
        self.target_draw_spin.setRange(1, 9999)
        side_form.addRow('대상 회차', self.target_draw_spin)

        self.generate_btn = QPushButton('번호 생성' if self.scope == 'generator' else '추천 실행')
        self.generate_btn.clicked.connect(self.run_generation)
        side_form.addRow(self.generate_btn)

        if self.enable_campaign:
            self.campaign_start_spin = QSpinBox()
            self.campaign_start_spin.setRange(1, 9999)
            side_form.addRow('캠페인 시작', self.campaign_start_spin)

            self.campaign_weeks_spin = QSpinBox()
            self.campaign_weeks_spin.setRange(1, APP_CONFIG['MAX_CAMPAIGN_WEEKS'])
            self.campaign_weeks_spin.setValue(4)
            side_form.addRow('캠페인 주차', self.campaign_weeks_spin)

            self.campaign_sets_spin = QSpinBox()
            self.campaign_sets_spin.setRange(1, APP_CONFIG['MAX_CAMPAIGN_SETS_PER_WEEK'])
            self.campaign_sets_spin.setValue(3)
            side_form.addRow('주당 세트', self.campaign_sets_spin)

            self.campaign_btn = QPushButton('캠페인 생성')
            self.campaign_btn.clicked.connect(self.run_campaign_generation)
            side_form.addRow(self.campaign_btn)

        top.addWidget(side, 1)
        layout.addLayout(top)

        self.results_table = QTableWidget(0, 5)
        self.results_table.setHorizontalHeaderLabels(['#', '번호', '점수', '합계', '설명'])
        vertical_header = self.results_table.verticalHeader()
        if vertical_header is not None:
            vertical_header.setVisible(False)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.results_table, 1)

        actions = QHBoxLayout()
        self.save_history_btn = QPushButton('히스토리 저장')
        self.save_history_btn.clicked.connect(self.save_all_history)
        actions.addWidget(self.save_history_btn)

        self.add_favorites_btn = QPushButton('선택 즐겨찾기')
        self.add_favorites_btn.clicked.connect(self.add_selected_to_favorites)
        actions.addWidget(self.add_favorites_btn)

        self.add_tickets_btn = QPushButton('전체 티켓북 추가')
        self.add_tickets_btn.clicked.connect(self.add_all_to_tickets)
        actions.addWidget(self.add_tickets_btn)
        actions.addStretch()
        layout.addLayout(actions)

        if self.scope == 'generator':
            self.set_count_spin.valueChanged.connect(self._persist_generator_options)
            self.fixed_input.textChanged.connect(self._persist_generator_options)
            self.exclude_input.textChanged.connect(self._persist_generator_options)

    def hydrate_defaults(self):
        self._is_hydrating = True
        try:
            pref = self.app_window.store.get_strategy_pref(self.scope)
            self.strategy_editor.apply_request(pref)
            next_draw = self.app_window.get_next_target_draw()
            self.target_draw_spin.setValue(next_draw)
            if self.enable_campaign:
                self.campaign_start_spin.setValue(next_draw)
            if self.scope == 'generator':
                options = self.app_window.store.get_generator_options()
                self.set_count_spin.setValue(int(options.get('num_sets') or 5))
                self.fixed_input.setPlainText(str(options.get('fixed_nums') or ''))
                self.exclude_input.setPlainText(str(options.get('exclude_nums') or ''))
                consecutive_limit = int(options.get('consecutive_limit') or 2)
                self.strategy_editor.max_consecutive_spin.setValue(
                    max(0, min(5, consecutive_limit)) if options.get('check_consecutive') else -1
                )
        finally:
            self._is_hydrating = False
        self._persist_generator_options()
        self.update_data_gate()

    def refresh_defaults(self):
        self.hydrate_defaults()

    def refresh_view_state(self):
        self.update_data_gate()

    def _persist_generator_options(self):
        if self.scope != 'generator' or self._is_hydrating:
            return
        request = self.strategy_editor.build_request()
        max_consecutive_pairs = request.get('filters', {}).get('maxConsecutivePairs')
        self.app_window.store.update_generator_options(
            num_sets=self.set_count_spin.value(),
            fixed_nums=self.fixed_input.toPlainText().strip(),
            exclude_nums=self.exclude_input.toPlainText().strip(),
            check_consecutive=max_consecutive_pairs is not None,
            consecutive_limit=0 if max_consecutive_pairs is None else int(max_consecutive_pairs),
        )

    def _on_preset_applied(self, _preset: Dict[str, Any]):
        self.app_window.store.set_strategy_pref(self.scope, self.strategy_editor.build_request())
        self._persist_generator_options()

    def update_data_gate(self):
        health = self.app_window.store.state.get('dataHealth') or {}
        availability = str(health.get('availability') or 'none')
        blocked = self.scope == 'ai' and availability != 'full'
        reason = str(health.get('message') or health.get('source') or '당첨 데이터 상태를 확인해 주세요.')

        self.strategy_editor.setEnabled(not blocked)
        self.generate_btn.setEnabled(not blocked)
        self.generate_btn.setToolTip('')
        if blocked:
            self.generate_btn.setToolTip(f'AI 추천은 full 데이터 상태에서만 사용할 수 있습니다. 현재 상태: {availability} / {reason}')
        if self.enable_campaign:
            self.campaign_btn.setEnabled(not blocked)
            self.campaign_btn.setToolTip(self.generate_btn.toolTip())

    def _parse_fixed_exclude(self) -> tuple[List[int], List[int]]:
        fixed = sorted(parse_number_expression(self.fixed_input.toPlainText(), '고정수'))
        exclude = sorted(parse_number_expression(self.exclude_input.toPlainText(), '제외수'))
        validation_error = validate_generation_constraints(
            fixed,
            exclude,
            max_fixed_nums=int(APP_CONFIG['MAX_FIXED_NUMS']),
        )
        if validation_error:
            raise ValueError(validation_error)
        return fixed, exclude

    def _show_input_error(self, message: str):
        QMessageBox.warning(self, '입력 오류', message)

    def _build_request(self) -> Dict[str, Any]:
        request = self.strategy_editor.build_request()
        self.app_window.store.set_strategy_pref(self.scope, request)
        return request

    def run_generation(self):
        if self.scope == 'ai' and not self.app_window.can_use_advanced_features(show_message=True):
            return
        try:
            fixed, exclude = self._parse_fixed_exclude()
            request = self._build_request()
            self._persist_generator_options()
        except ValueError as exc:
            self._show_input_error(str(exc))
            return
        count = self.set_count_spin.value()

        def task() -> List[Dict[str, Any]]:
            engine = StrategyEngine(self.app_window.stats_manager.winning_data)
            sets = engine.generate_multiple_sets(count, request, {'fixed': fixed, 'exclude': exclude, 'maxAttempts': 320})
            rows = []
            for numbers in sets:
                explanation = engine.explain_set(numbers, request) or {}
                rows.append({
                    'numbers': numbers,
                    'score': float(explanation.get('summary', {}).get('recommendationScore', 0.0)),
                    'sum': int(explanation.get('summary', {}).get('sum', sum(numbers))),
                    'explanation': explanation,
                    'request': request,
                })
            return rows

        self._run_task(task, self._on_generated)

    def run_campaign_generation(self):
        if not self.enable_campaign:
            return
        if self.scope == 'ai' and not self.app_window.can_use_advanced_features(show_message=True):
            return
        try:
            fixed, exclude = self._parse_fixed_exclude()
            request = self._build_request()
            self._persist_generator_options()
        except ValueError as exc:
            self._show_input_error(str(exc))
            return
        start_draw = self.campaign_start_spin.value()
        weeks = self.campaign_weeks_spin.value()
        sets_per_week = self.campaign_sets_spin.value()

        def task() -> Dict[str, Any]:
            engine = StrategyEngine(self.app_window.stats_manager.winning_data)
            tickets = []
            for week_index in range(weeks):
                runtime_request = {
                    **request,
                    'params': {**(request.get('params') or {}), 'seed': None if request.get('params', {}).get('seed') is None else int(request['params']['seed']) + week_index},
                }
                sets = engine.generate_multiple_sets(sets_per_week, runtime_request, {'fixed': fixed, 'exclude': exclude, 'maxAttempts': 360})
                for numbers in sets:
                    tickets.append({
                        'numbers': numbers,
                        'targetDrawNo': start_draw + week_index,
                        'source': self.scope,
                        'strategyRequest': runtime_request,
                        'campaignId': '',
                        'memo': f'{start_draw}회 시작 {weeks}주 캠페인',
                        'quantity': 1,
                    })
            return {'tickets': tickets, 'startDrawNo': start_draw, 'weeks': weeks, 'setsPerWeek': sets_per_week, 'request': request}

        self._run_task(task, self._on_campaign_generated)

    def _run_task(self, fn: Callable[[], Any], on_success: Callable[[Any], None]):
        self.generate_btn.setEnabled(False)
        if self.enable_campaign:
            self.campaign_btn.setEnabled(False)
        thread = TaskThread(fn, self)
        self._task = thread
        thread.resultReady.connect(lambda payload: self._finish_task(payload, on_success))
        thread.errorOccurred.connect(self._on_task_error)
        thread.finished.connect(lambda: self._set_busy(False))
        self._set_busy(True)
        thread.start()

    def _set_busy(self, busy: bool):
        self.generate_btn.setEnabled(not busy)
        if self.enable_campaign:
            self.campaign_btn.setEnabled(not busy)

    def _finish_task(self, payload: Any, on_success: Callable[[Any], None]):
        self._set_busy(False)
        on_success(payload)

    def _on_task_error(self, message: str):
        self._set_busy(False)
        QMessageBox.warning(self, '작업 실패', message)

    def _on_generated(self, rows: List[Dict[str, Any]]):
        self.generated_rows = rows
        self.results_table.setRowCount(0)
        for index, row in enumerate(rows, start=1):
            current = self.results_table.rowCount()
            self.results_table.insertRow(current)
            self.results_table.setItem(current, 0, QTableWidgetItem(str(index)))
            self.results_table.setItem(current, 1, QTableWidgetItem(', '.join(str(value) for value in row['numbers'])))
            self.results_table.setItem(current, 2, QTableWidgetItem(f"{row['score']:.4f}"))
            self.results_table.setItem(current, 3, QTableWidgetItem(str(row['sum'])))
            self.results_table.setItem(current, 4, QTableWidgetItem(self._format_explanation(row['explanation'])))
        self.app_window.show_status(f'{len(rows)}개 세트를 생성했습니다.', 4000)

    def _on_campaign_generated(self, payload: Dict[str, Any]):
        tickets = payload['tickets']
        if not tickets:
            QMessageBox.information(self, '캠페인', '생성된 티켓이 없습니다.')
            return
        campaign_id = self.app_window.store.create_id('campaign')
        for ticket in tickets:
            ticket['campaignId'] = campaign_id
        self.app_window.store.add_tickets_bulk(tickets, winning_data=self.app_window.stats_manager.winning_data)
        self.app_window.store.add_campaign({
            'id': campaign_id,
            'name': f"{payload['startDrawNo']}회 시작 {payload['weeks']}주",
            'startDrawNo': payload['startDrawNo'],
            'weeks': payload['weeks'],
            'setsPerWeek': payload['setsPerWeek'],
            'strategyRequest': payload['request'],
        })
        self.app_window.refresh_all_views()
        QMessageBox.information(self, '캠페인 완료', f"티켓 {len(tickets)}개와 캠페인을 저장했습니다.")

    def _format_explanation(self, explanation: Dict[str, Any]) -> str:
        summary = explanation.get('summary', {}) if isinstance(explanation, dict) else {}
        pair = summary.get('pairSynergy', 0)
        profile = summary.get('profileScore', 0)
        gap = summary.get('gapBalanceScore', 0)
        return f'페어 {pair:.3f} / 프로파일 {profile:.3f} / 공백 {gap:.3f}'

    def _selected_rows(self) -> List[Dict[str, Any]]:
        indexes = sorted({item.row() for item in self.results_table.selectedItems()})
        if not indexes:
            return list(self.generated_rows)
        return [self.generated_rows[index] for index in indexes if 0 <= index < len(self.generated_rows)]

    def save_all_history(self):
        if not self.generated_rows:
            return
        entries = [{'numbers': row['numbers'], 'date': dt.datetime.now().isoformat()} for row in self.generated_rows]
        self.app_window.store.add_history_many(entries)
        self.app_window.refresh_all_views()
        self.app_window.show_status('생성 결과를 히스토리에 저장했습니다.', 4000)

    def add_selected_to_favorites(self):
        rows = self._selected_rows()
        added = 0
        for row in rows:
            if self.app_window.store.add_favorite(row['numbers'], save=False):
                added += 1
        if added:
            self.app_window.store.save()
        self.app_window.refresh_all_views()
        self.app_window.show_status(f'즐겨찾기 {added}개 추가', 4000)

    def add_all_to_tickets(self):
        if not self.generated_rows:
            return
        target_draw = self.target_draw_spin.value()
        tickets = [
            {
                'numbers': row['numbers'],
                'targetDrawNo': target_draw,
                'source': self.scope,
                'strategyRequest': row['request'],
                'memo': f'{self.scope} generated',
                'quantity': 1,
            }
            for row in self.generated_rows
        ]
        self.app_window.store.add_tickets_bulk(tickets, winning_data=self.app_window.stats_manager.winning_data)
        self.app_window.refresh_all_views()
        self.app_window.show_status(f'티켓북에 {len(tickets)}개 추가', 4000)


