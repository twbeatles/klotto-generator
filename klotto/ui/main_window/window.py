from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from PyQt6.QtCore import QByteArray, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
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
from klotto.core.draws import estimate_latest_draw
from klotto.core.lotto_rules import parse_number_expression, validate_generation_constraints
from klotto.core.stats import WinningStatsManager
from klotto.core.sync_service import LottoSyncWorker
from klotto.core.strategy_engine import StrategyEngine
from klotto.data.app_state import get_shared_store
from klotto.data.exporter import DataExporter
from klotto.data.favorites import FavoritesManager
from klotto.data.history import HistoryManager
from klotto.logging import logger
from klotto.ui.dialogs import ExportImportDialog, WinningCheckDialog
from klotto.ui.scanner import QRCodeScannerDialog
from klotto.ui.theme import ThemeManager
from klotto.ui.widgets import StrategyRequestEditor, WinningInfoWidget


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


class NumberGenerationPage(QWidget):
    def __init__(self, app_window: 'LottoApp', scope: str, title: str, *, enable_campaign: bool = False):
        super().__init__(app_window)
        self.app_window = app_window
        self.scope = scope
        self.enable_campaign = enable_campaign
        self.generated_rows: List[Dict[str, Any]] = []
        self._task: Optional[TaskThread] = None
        self._generator_options_loaded = False
        self._setup_ui(title)
        self.refresh_defaults()

    def _setup_ui(self, title: str):
        layout = QVBoxLayout(self)
        if self.scope == 'generator':
            self.winning_info_widget = WinningInfoWidget(self.app_window.stats_manager)
            self.winning_info_widget.dataLoaded.connect(lambda _payload: self.app_window.refresh_all_views())
            layout.addWidget(self.winning_info_widget)

        header = QLabel(title)
        header.setFont(QFont('Segoe UI', 16, QFont.Weight.Bold))
        layout.addWidget(header)

        top = QHBoxLayout()
        self.strategy_editor = StrategyRequestEditor(self.scope, '전략 / 필터')
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

    def refresh_defaults(self):
        pref = self.app_window.store.get_strategy_pref(self.scope)
        self.strategy_editor.apply_request(pref)
        if self.scope == 'generator' and not self._generator_options_loaded:
            self._apply_generator_options()
            self._generator_options_loaded = True
        next_draw = self.app_window.get_next_target_draw()
        self.target_draw_spin.setValue(next_draw)
        if self.enable_campaign:
            self.campaign_start_spin.setValue(next_draw)
        self.update_data_gate()

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

    def _build_request(self) -> Dict[str, Any]:
        request = self.strategy_editor.build_request()
        self.app_window.store.set_strategy_pref(self.scope, request)
        return request

    def _apply_generator_options(self):
        options = self.app_window.store.normalize_generator_options(self.app_window.store.state.get('generatorOptions') or {})
        self.app_window.store.state['generatorOptions'] = options
        self.set_count_spin.setValue(int(options.get('num_sets') or 5))
        self.fixed_input.setPlainText(str(options.get('fixed_nums') or ''))
        self.exclude_input.setPlainText(str(options.get('exclude_nums') or ''))
        if bool(options.get('check_consecutive', True)):
            self.strategy_editor.max_consecutive_spin.setValue(int(options.get('consecutive_limit') or 2))
        else:
            self.strategy_editor.max_consecutive_spin.setValue(-1)

    def _persist_generator_options(self, request: Dict[str, Any]):
        if self.scope != 'generator':
            return
        filter_value = request.get('filters')
        filters: Dict[str, Any] = filter_value if isinstance(filter_value, dict) else {}
        consecutive_limit = filters.get('maxConsecutivePairs')
        check_consecutive = consecutive_limit is not None
        raw_options = {
            'num_sets': self.set_count_spin.value(),
            'fixed_nums': self.fixed_input.toPlainText(),
            'exclude_nums': self.exclude_input.toPlainText(),
            'check_consecutive': check_consecutive,
            'consecutive_limit': consecutive_limit if check_consecutive else 2,
        }
        self.app_window.store.state['generatorOptions'] = self.app_window.store.normalize_generator_options(raw_options)
        self.app_window.store.save()

    def _show_input_error(self, message: str):
        QMessageBox.warning(self, '입력 오류', message)

    def run_generation(self):
        if self.scope == 'ai' and not self.app_window.can_use_advanced_features(show_message=True):
            return
        try:
            fixed, exclude = self._parse_fixed_exclude()
            request = self._build_request()
            self._persist_generator_options(request)
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
            self._persist_generator_options(request)
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

class StatsPage(QWidget):
    def __init__(self, app_window: 'LottoApp'):
        super().__init__(app_window)
        self.app_window = app_window
        layout = QVBoxLayout(self)
        self.summary_label = QLabel('통계를 불러오는 중...')
        layout.addWidget(self.summary_label)
        self.hot_table = QTableWidget(0, 2)
        self.hot_table.setHorizontalHeaderLabels(['핫 넘버', '출현'])
        self.cold_table = QTableWidget(0, 2)
        self.cold_table.setHorizontalHeaderLabels(['콜드 넘버', '출현'])
        row = QHBoxLayout()
        row.addWidget(self.hot_table)
        row.addWidget(self.cold_table)
        layout.addLayout(row)
        self.recent_table = QTableWidget(0, 4)
        self.recent_table.setHorizontalHeaderLabels(['회차', '날짜', '번호', '보너스'])
        layout.addWidget(self.recent_table, 1)

    def refresh_data(self):
        stats = self.app_window.stats_manager.get_frequency_analysis()
        winning_data = self.app_window.stats_manager.winning_data
        total_draws = len(winning_data)
        latest_draw = winning_data[0]['draw_no'] if winning_data else 0
        health = self.app_window.store.state['dataHealth']
        self.summary_label.setText(f"총 {total_draws}회차 | 최신 {latest_draw}회 | 데이터 상태: {health.get('availability')} ({health.get('message') or health.get('source')})")
        most_common = stats.get('most_common', []) if isinstance(stats, dict) else []
        least_common = stats.get('least_common', []) if isinstance(stats, dict) else []
        self._fill_rank_table(self.hot_table, most_common)
        self._fill_rank_table(self.cold_table, least_common)
        self.recent_table.setRowCount(0)
        for draw in winning_data[:12]:
            row = self.recent_table.rowCount()
            self.recent_table.insertRow(row)
            self.recent_table.setItem(row, 0, QTableWidgetItem(str(draw.get('draw_no'))))
            self.recent_table.setItem(row, 1, QTableWidgetItem(str(draw.get('date') or '-')))
            self.recent_table.setItem(row, 2, QTableWidgetItem(', '.join(str(value) for value in draw.get('numbers', []))))
            self.recent_table.setItem(row, 3, QTableWidgetItem(str(draw.get('bonus') or '-')))

    def _fill_rank_table(self, table: QTableWidget, rows: Sequence[Any]):
        table.setRowCount(0)
        for rank in rows[:10]:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(str(rank[0])))
            table.setItem(row, 1, QTableWidgetItem(str(rank[1])))


class BacktestPage(QWidget):
    def __init__(self, app_window: 'LottoApp'):
        super().__init__(app_window)
        self.app_window = app_window
        self._task: Optional[TaskThread] = None
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.strategy_editor = StrategyRequestEditor('backtest', '전략 기준값')
        self.strategy_editor.strategiesChanged.connect(self.refresh_strategy_list)
        top.addWidget(self.strategy_editor, 2)

        side = QGroupBox('백테스트 실행')
        side_form = QFormLayout(side)
        self.start_draw_spin = QSpinBox()
        self.start_draw_spin.setRange(1, 9999)
        side_form.addRow('시작 회차', self.start_draw_spin)
        self.end_draw_spin = QSpinBox()
        self.end_draw_spin.setRange(1, 9999)
        side_form.addRow('종료 회차', self.end_draw_spin)
        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, 20)
        self.qty_spin.setValue(5)
        side_form.addRow('회차당 티켓 수', self.qty_spin)
        self.strategy_list = QListWidget()
        self.strategy_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        side_form.addRow('비교 전략', self.strategy_list)
        self.run_btn = QPushButton('시뮬레이션 실행')
        self.run_btn.clicked.connect(self.run_backtest)
        side_form.addRow(self.run_btn)
        top.addWidget(side, 1)
        layout.addLayout(top)

        self.result_table = QTableWidget(0, 7)
        self.result_table.setHorizontalHeaderLabels(['전략', 'ROI', '적중률', '회차', '티켓', '총상금', '총비용'])
        layout.addWidget(self.result_table, 1)
        self.refresh_defaults()

    def refresh_defaults(self):
        pref = self.app_window.store.get_strategy_pref('backtest')
        self.strategy_editor.apply_request(pref)
        latest = self.app_window.get_latest_draw_no()
        self.start_draw_spin.setValue(max(1, latest - 30))
        self.end_draw_spin.setValue(latest)
        self.refresh_strategy_list()
        self.update_data_gate()

    def refresh_strategy_list(self):
        selected_ids = {
            str(item.data(Qt.ItemDataRole.UserRole))
            for item in self.strategy_list.selectedItems()
            if item.data(Qt.ItemDataRole.UserRole)
        }
        self.strategy_list.clear()
        for index in range(self.strategy_editor.strategy_combo.count()):
            item = QListWidgetItem(self.strategy_editor.strategy_combo.itemText(index))
            item.setData(Qt.ItemDataRole.UserRole, self.strategy_editor.strategy_combo.itemData(index))
            if str(item.data(Qt.ItemDataRole.UserRole)) in selected_ids:
                item.setSelected(True)
            self.strategy_list.addItem(item)
        if self.strategy_list.count() > 0 and not self.strategy_list.selectedItems():
            first_item = self.strategy_list.item(0)
            if first_item is not None:
                first_item.setSelected(True)

    def update_data_gate(self):
        allowed = self.app_window.is_data_health_full()
        health = self.app_window.store.state.get('dataHealth') or {}
        reason = str(health.get('message') or health.get('source') or '당첨 데이터 상태를 확인해 주세요.')
        self.strategy_editor.setEnabled(allowed)
        self.strategy_list.setEnabled(allowed)
        self.run_btn.setEnabled(allowed)
        self.run_btn.setToolTip('' if allowed else f'전략 시뮬레이션은 full 데이터 상태에서만 사용할 수 있습니다. {reason}')

    def run_backtest(self):
        if not self.app_window.can_use_advanced_features(show_message=True):
            return
        request = self.strategy_editor.build_request()
        selected_ids = [item.data(Qt.ItemDataRole.UserRole) for item in self.strategy_list.selectedItems()]
        if not selected_ids:
            selected_ids = [request['strategyId']]
        strategy_requests = []
        for strategy_id in selected_ids[: APP_CONFIG['MAX_COMPARE_STRATEGIES']]:
            strategy_requests.append({**request, 'strategyId': strategy_id})
        self.app_window.store.set_strategy_pref('backtest', request)

        def task() -> Dict[str, Any]:
            result = run_backtest(
                self.app_window.stats_manager.winning_data,
                self.start_draw_spin.value(),
                self.end_draw_spin.value(),
                self.qty_spin.value(),
                strategy_requests=strategy_requests,
                payout_mode=request.get('params', {}).get('payoutMode', 'hybrid_dynamic_first'),
            )
            return {'summary': result.summary, 'comparisons': result.comparisons, 'diagnostics': result.diagnostics}

        self.run_btn.setEnabled(False)
        thread = TaskThread(task, self)
        self._task = thread
        thread.resultReady.connect(self._on_backtest_ready)
        thread.errorOccurred.connect(lambda message: QMessageBox.warning(self, '백테스트 실패', message))
        thread.finished.connect(lambda: self.run_btn.setEnabled(True))
        thread.start()

    def _on_backtest_ready(self, payload: Dict[str, Any]):
        self.result_table.setRowCount(0)
        for row_data in payload.get('comparisons', []):
            row = self.result_table.rowCount()
            self.result_table.insertRow(row)
            self.result_table.setItem(row, 0, QTableWidgetItem(str(row_data.get('strategyId'))))
            self.result_table.setItem(row, 1, QTableWidgetItem(f"{float(row_data.get('roi', 0)):.2f}%"))
            self.result_table.setItem(row, 2, QTableWidgetItem(f"{float(row_data.get('hitRate', 0)):.2f}%"))
            self.result_table.setItem(row, 3, QTableWidgetItem(str(row_data.get('draws', 0))))
            self.result_table.setItem(row, 4, QTableWidgetItem(str(row_data.get('tickets', 0))))
            self.result_table.setItem(row, 5, QTableWidgetItem(f"{int(row_data.get('totalPrize', 0)):,}"))
            self.result_table.setItem(row, 6, QTableWidgetItem(f"{int(row_data.get('cost', 0)):,}"))
        self.app_window.show_status('백테스트가 완료되었습니다.', 4000)


class CheckPage(QWidget):
    def __init__(self, app_window: 'LottoApp'):
        super().__init__(app_window)
        self.app_window = app_window
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.source_list = QListWidget()
        self.source_list.currentRowChanged.connect(self.refresh_items)
        self.source_list.addItems(['즐겨찾기', '히스토리', '티켓북'])
        controls.addWidget(self.source_list, 1)
        self.item_list = QListWidget()
        controls.addWidget(self.item_list, 2)
        layout.addLayout(controls)

        button_row = QHBoxLayout()
        self.check_btn = QPushButton('당첨 확인')
        self.check_btn.clicked.connect(self.run_check)
        button_row.addWidget(self.check_btn)
        self.qr_scan_btn = QPushButton('QR 스캔')
        self.qr_scan_btn.clicked.connect(self.open_qr_scanner)
        button_row.addWidget(self.qr_scan_btn)
        layout.addLayout(button_row)

        self.results_table = QTableWidget(0, 5)
        self.results_table.setHorizontalHeaderLabels(['설명', '회차', '일치', '순위', '비고'])
        layout.addWidget(self.results_table, 1)
        self.source_list.setCurrentRow(0)

    def refresh_sources(self):
        self.refresh_items(self.source_list.currentRow())

    def refresh_items(self, _row: int):
        self.item_list.clear()
        source = self.source_list.currentRow()
        if source == 0:
            for favorite in self.app_window.store.state['favorites']:
                self.item_list.addItem(', '.join(str(value) for value in favorite['numbers']))
        elif source == 1:
            for history in self.app_window.store.state['history']:
                self.item_list.addItem(', '.join(str(value) for value in history['numbers']))
        else:
            for ticket in self.app_window.store.state['ticketBook']:
                label = f"{ticket['targetDrawNo']}회차 | {', '.join(str(value) for value in ticket['numbers'])}"
                self.item_list.addItem(label)

    def run_check(self):
        row = self.item_list.currentRow()
        if row < 0:
            return
        source = self.source_list.currentRow()
        if source == 0:
            numbers = self.app_window.store.state['favorites'][row]['numbers']
            results = self.app_window.check_numbers_against_history(numbers)
        elif source == 1:
            numbers = self.app_window.store.state['history'][row]['numbers']
            results = self.app_window.check_numbers_against_history(numbers)
        else:
            ticket = self.app_window.store.state['ticketBook'][row]
            results = self.app_window.check_ticket(ticket)
        self.results_table.setRowCount(0)
        for item in results:
            next_row = self.results_table.rowCount()
            self.results_table.insertRow(next_row)
            self.results_table.setItem(next_row, 0, QTableWidgetItem(str(item.get('label'))))
            self.results_table.setItem(next_row, 1, QTableWidgetItem(str(item.get('drawNo'))))
            self.results_table.setItem(next_row, 2, QTableWidgetItem(str(item.get('matches'))))
            self.results_table.setItem(next_row, 3, QTableWidgetItem(str(item.get('rank'))))
            self.results_table.setItem(next_row, 4, QTableWidgetItem(str(item.get('note') or '')))

    def open_qr_scanner(self):
        scanner = QRCodeScannerDialog(self)
        if scanner.exec() != QDialog.DialogCode.Accepted:
            return
        payload = scanner.scanned_data
        if not payload:
            QMessageBox.warning(self, 'QR 스캔', '스캔된 QR 데이터가 없습니다.')
            return
        dialog = WinningCheckDialog(
            self.app_window.favorites_manager,
            self.app_window.history_manager,
            self.app_window.stats_manager,
            self,
            qr_payload=payload,
        )
        dialog.exec()


class DataPage(QWidget):
    def __init__(self, app_window: 'LottoApp'):
        super().__init__(app_window)
        self.app_window = app_window
        layout = QVBoxLayout(self)
        actions = QHBoxLayout()
        self.export_backup_btn = QPushButton('전체 백업 내보내기')
        self.export_backup_btn.clicked.connect(self.export_backup)
        actions.addWidget(self.export_backup_btn)
        self.import_backup_btn = QPushButton('전체 백업 가져오기')
        self.import_backup_btn.clicked.connect(self.import_backup)
        actions.addWidget(self.import_backup_btn)
        self.legacy_btn = QPushButton('레거시 가져오기/내보내기')
        self.legacy_btn.clicked.connect(self.open_legacy_dialog)
        actions.addWidget(self.legacy_btn)
        self.export_excel_btn = QPushButton('당첨 DB 엑셀 내보내기')
        self.export_excel_btn.clicked.connect(self.export_winning_excel)
        actions.addWidget(self.export_excel_btn)
        self.remove_btn = QPushButton('선택 항목 삭제')
        self.remove_btn.clicked.connect(self.remove_selected)
        actions.addWidget(self.remove_btn)
        self.clear_btn = QPushButton('현재 탭 비우기')
        self.clear_btn.clicked.connect(self.clear_current_tab)
        actions.addWidget(self.clear_btn)
        actions.addStretch()
        layout.addLayout(actions)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.tables: Dict[str, QTableWidget] = {}
        for name, headers in {
            'favorites': ['번호', '메모', '생성일'],
            'history': ['번호', '기록일'],
            'tickets': ['회차', '번호', '수량', '상태'],
            'campaigns': ['이름', '시작', '주차', '세트/주'],
        }.items():
            table = QTableWidget(0, len(headers))
            table.setHorizontalHeaderLabels(headers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            self.tables[name] = table
            wrapper = QWidget()
            wrapper_layout = QVBoxLayout(wrapper)
            wrapper_layout.addWidget(table)
            self.tabs.addTab(wrapper, name)

    def refresh_tables(self):
        self._fill_table(self.tables['favorites'], [[', '.join(str(v) for v in item['numbers']), item.get('memo', ''), item.get('created_at', '')] for item in self.app_window.store.state['favorites']])
        self._fill_table(self.tables['history'], [[', '.join(str(v) for v in item['numbers']), item.get('date', '')] for item in self.app_window.store.state['history']])
        self._fill_table(self.tables['tickets'], [[str(item.get('targetDrawNo')), ', '.join(str(v) for v in item.get('numbers', [])), str(item.get('quantity', 1)), self._ticket_status(item)] for item in self.app_window.store.state['ticketBook']])
        self._fill_table(self.tables['campaigns'], [[item.get('name', ''), str(item.get('startDrawNo', '')), str(item.get('weeks', '')), str(item.get('setsPerWeek', ''))] for item in self.app_window.store.state['campaigns']])

    def _fill_table(self, table: QTableWidget, rows: Sequence[Sequence[str]]):
        table.setRowCount(0)
        for row_values in rows:
            row = table.rowCount()
            table.insertRow(row)
            for col, value in enumerate(row_values):
                table.setItem(row, col, QTableWidgetItem(str(value)))

    def current_dataset_name(self) -> str:
        names = ['favorites', 'history', 'tickets', 'campaigns']
        index = self.tabs.currentIndex()
        return names[index] if 0 <= index < len(names) else 'favorites'

    def remove_selected(self):
        dataset = self.current_dataset_name()
        table = self.tables[dataset]
        row = table.currentRow()
        if row < 0:
            QMessageBox.information(self, '데이터 관리', '삭제할 행을 선택해 주세요.')
            return
        removed = False
        if dataset == 'favorites':
            removed = self.app_window.store.remove_favorite(row)
        elif dataset == 'history':
            if 0 <= row < len(self.app_window.store.state['history']):
                self.app_window.store.state['history'].pop(row)
                self.app_window.store.save()
                removed = True
        elif dataset == 'tickets':
            ticket = self.app_window.store.state['ticketBook'][row]
            removed = self.app_window.store.remove_ticket(str(ticket.get('id') or ''))
        elif dataset == 'campaigns':
            campaign = self.app_window.store.state['campaigns'][row]
            result = self.app_window.store.remove_campaign(str(campaign.get('id') or ''), cascade_tickets=True)
            removed = bool(result.get('removedCampaign') or result.get('removedTickets'))
        if removed:
            self.app_window.refresh_all_views()
            self.app_window.show_status('선택 항목을 삭제했습니다.', 4000)

    def clear_current_tab(self):
        dataset = self.current_dataset_name()
        removed = 0
        if dataset == 'favorites':
            removed = len(self.app_window.store.state['favorites'])
            self.app_window.store.clear_favorites()
        elif dataset == 'history':
            removed = len(self.app_window.store.state['history'])
            self.app_window.store.clear_history()
        elif dataset == 'tickets':
            removed = self.app_window.store.clear_ticket_book('all')
        elif dataset == 'campaigns':
            result = self.app_window.store.clear_campaigns(cascade_tickets=True)
            removed = int(result.get('removedCampaigns', 0))
        self.app_window.refresh_all_views()
        self.app_window.show_status(f'{dataset} 정리 완료 ({removed})', 4000)

    def _ticket_status(self, ticket: Dict[str, Any]) -> str:
        checked = ticket.get('checked')
        if not checked:
            return '예정'
        return '당첨' if int(checked.get('rank', 0)) > 0 else '미당첨'

    def export_backup(self):
        filepath, _ = QFileDialog.getSaveFileName(self, '백업 저장', 'lotto_app_backup.json', 'JSON 파일 (*.json)')
        if not filepath:
            return
        payload = self.app_window.store.export_backup_payload()
        if DataExporter.export_any_json(payload, filepath):
            self.app_window.show_status('전체 백업을 저장했습니다.', 4000)

    def import_backup(self):
        filepath, _ = QFileDialog.getOpenFileName(self, '백업 가져오기', '', 'JSON 파일 (*.json)')
        if not filepath:
            return
        payload = DataExporter.import_any_json(filepath)
        if not isinstance(payload, dict):
            QMessageBox.warning(self, '가져오기', '백업 파일 형식이 올바르지 않습니다.')
            return
        self.app_window.store.import_backup_payload(payload, winning_data=self.app_window.stats_manager.winning_data)
        self.app_window.refresh_all_views()
        self.app_window.show_status('백업을 불러왔습니다.', 4000)

    def export_winning_excel(self):
        filepath, _ = QFileDialog.getSaveFileName(self, '당첨 DB 엑셀 저장', 'lotto_history.xlsx', 'Excel 파일 (*.xlsx)')
        if not filepath:
            return
        try:
            from scripts.export_to_excel import ensure_openpyxl, export_to_excel
        except Exception as exc:
            logger.exception('Excel exporter import failed')
            QMessageBox.warning(self, '엑셀 내보내기', f'엑셀 내보내기 기능을 초기화하지 못했습니다.\n{exc}')
            return

        if not ensure_openpyxl():
            QMessageBox.warning(self, '엑셀 내보내기', '엑셀 내보내기에는 requirements-optional.txt의 openpyxl 설치가 필요합니다.')
            return

        db_path = Path(APP_CONFIG['LOTTO_HISTORY_DB'])
        if not db_path.exists():
            QMessageBox.warning(self, '엑셀 내보내기', f'당첨번호 데이터베이스를 찾을 수 없습니다.\n{db_path}')
            return

        if export_to_excel(Path(filepath)):
            self.app_window.show_status('당첨 DB를 엑셀로 저장했습니다.', 4000)
        else:
            QMessageBox.warning(self, '엑셀 내보내기', '내보낼 당첨 데이터가 없거나 저장에 실패했습니다.')

    def open_legacy_dialog(self):
        dialog = ExportImportDialog(self.app_window.favorites_manager, self.app_window.history_manager, self.app_window.stats_manager, self)
        dialog.exec()
        self.app_window.refresh_all_views()


class SettingsPage(QWidget):
    syncRequested = pyqtSignal()

    def __init__(self, app_window: 'LottoApp'):
        super().__init__(app_window)
        self.app_window = app_window
        layout = QVBoxLayout(self)
        self.health_label = QLabel()
        self.sync_label = QLabel()
        layout.addWidget(self.health_label)
        layout.addWidget(self.sync_label)
        self.sync_btn = QPushButton('지금 동기화')
        self.sync_btn.clicked.connect(self.syncRequested.emit)
        layout.addWidget(self.sync_btn)
        self.theme_btn = QPushButton('라이트/다크 전환')
        self.theme_btn.clicked.connect(self.app_window.toggle_theme)
        layout.addWidget(self.theme_btn)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)

    def refresh_status(self):
        health = self.app_window.store.state['dataHealth']
        sync_meta = self.app_window.store.state['syncMeta']
        self.health_label.setText(f"데이터 상태: {health.get('availability')} | 최신 회차 {health.get('latestDrawNo')} | {health.get('message') or health.get('source')}")
        self.sync_label.setText(f"동기화 모드: {sync_meta.get('mode')} | 마지막 성공: {sync_meta.get('lastSuccessAt')} | 마지막 반영 회차: {sync_meta.get('lastSuccessDrawNo')}")

    def append_log(self, message: str):
        self.log.append(message)

class LottoApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.store = get_shared_store()
        self.favorites_manager = FavoritesManager(self.store)
        self.history_manager = HistoryManager(self.store)
        self.stats_manager = WinningStatsManager()
        self._active_sync_worker: Optional[LottoSyncWorker] = None
        ThemeManager.set_theme_name(self.store.state.get('theme', 'light'))
        ThemeManager.add_listener(self.apply_theme)
        self._setup_ui()
        self.refresh_data_health()
        self.refresh_all_views()

    def _setup_ui(self):
        self.setWindowTitle(f"{APP_CONFIG['APP_NAME']} v{APP_CONFIG['VERSION']}")
        self.resize(*APP_CONFIG['WINDOW_SIZE'])
        central = QWidget()
        root = QHBoxLayout(central)
        splitter = QSplitter()
        root.addWidget(splitter)

        nav_panel = QWidget()
        nav_layout = QVBoxLayout(nav_panel)
        title = QLabel(APP_CONFIG['APP_NAME'])
        title.setFont(QFont('Segoe UI', 18, QFont.Weight.Bold))
        nav_layout.addWidget(title)
        subtitle = QLabel('Desktop Sync Edition')
        nav_layout.addWidget(subtitle)
        self.nav_list = QListWidget()
        self.nav_list.addItems(['생성', '당첨 통계', 'AI 추천', '전략 시뮬레이션', '당첨 확인', '데이터 관리', '설정/동기화'])
        nav_layout.addWidget(self.nav_list, 1)
        self.theme_toggle_btn = QPushButton('테마 전환')
        self.theme_toggle_btn.clicked.connect(self.toggle_theme)
        nav_layout.addWidget(self.theme_toggle_btn)
        splitter.addWidget(nav_panel)

        self.stack = QStackedWidget()
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)

        self.generator_page = NumberGenerationPage(self, 'generator', '번호 생성', enable_campaign=True)
        self.stats_page = StatsPage(self)
        self.ai_page = NumberGenerationPage(self, 'ai', 'AI 추천', enable_campaign=False)
        self.backtest_page = BacktestPage(self)
        self.check_page = CheckPage(self)
        self.data_page = DataPage(self)
        self.settings_page = SettingsPage(self)
        self.settings_page.syncRequested.connect(self.start_sync)

        for page in [self.generator_page, self.stats_page, self.ai_page, self.backtest_page, self.check_page, self.data_page, self.settings_page]:
            self.stack.addWidget(page)

        self.nav_list.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav_list.setCurrentRow(0)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        geometry = self.store.state.get('windowGeometry')
        if isinstance(geometry, str) and geometry:
            try:
                restored = self.restoreGeometry(QByteArray.fromBase64(geometry.encode('ascii')))
                if not restored:
                    logger.warning('Stored window geometry could not be restored')
            except Exception as exc:
                logger.warning('Stored window geometry is invalid: %s', exc)
        self.apply_theme()

    def apply_theme(self):
        self.setStyleSheet(ThemeManager.get_stylesheet())
        self.store.state['theme'] = ThemeManager.get_theme_name()
        self.store.save()

    def toggle_theme(self):
        ThemeManager.toggle_theme()

    def get_latest_draw_no(self) -> int:
        return int(self.stats_manager.winning_data[0]['draw_no']) if self.stats_manager.winning_data else max(1, estimate_latest_draw() - 1)

    def get_next_target_draw(self) -> int:
        return self.get_latest_draw_no() + 1

    def show_status(self, message: str, timeout: int = 4000) -> None:
        status_bar = self.statusBar()
        if status_bar is not None:
            status_bar.showMessage(message, timeout)

    def is_data_health_full(self) -> bool:
        return str((self.store.state.get('dataHealth') or {}).get('availability') or 'none') == 'full'

    def can_use_advanced_features(self, *, show_message: bool = False) -> bool:
        allowed = self.is_data_health_full()
        if not allowed and show_message:
            health = self.store.state.get('dataHealth') or {}
            QMessageBox.information(
                self,
                '데이터 상태 필요',
                'AI 추천과 전략 시뮬레이션은 전체 당첨 이력이 확보된 상태에서만 사용할 수 있습니다.\n\n'
                f"현재 상태: {health.get('availability')}\n"
                f"세부 정보: {health.get('message') or health.get('source')}",
            )
        return allowed

    def refresh_data_health(self):
        winning_data = self.stats_manager.winning_data
        if not winning_data:
            self.store.state['dataHealth'] = {'availability': 'none', 'source': 'none', 'latestDrawNo': 0, 'message': '당첨 데이터가 없습니다.'}
            self.store.save()
            return
        latest_draw = max(int(draw.get('draw_no', 0)) for draw in winning_data)
        existing = {int(draw.get('draw_no', 0)) for draw in winning_data}
        allowed_missing = set(APP_CONFIG['ALLOWED_MISSING_DRAWS'])
        missing = [draw_no for draw_no in range(1, latest_draw + 1) if draw_no not in existing and draw_no not in allowed_missing]
        expected_latest = estimate_latest_draw()
        is_full = latest_draw >= (expected_latest - int(APP_CONFIG['LATEST_DRAW_STALE_THRESHOLD'])) and len(missing) == 0
        availability = 'full' if is_full else 'partial'
        message = '전체 당첨 이력 확보' if is_full else f'누락 {len(missing)}회 / 예상 최신 {expected_latest}회'
        self.store.state['dataHealth'] = {'availability': availability, 'source': 'sqlite_db', 'latestDrawNo': latest_draw, 'message': message}
        self.store.save()

    def refresh_all_views(self):
        self.refresh_data_health()
        self.stats_page.refresh_data()
        self.generator_page.refresh_defaults()
        self.ai_page.refresh_defaults()
        self.backtest_page.refresh_defaults()
        self.ai_page.update_data_gate()
        self.backtest_page.update_data_gate()
        self.check_page.refresh_sources()
        self.data_page.refresh_tables()
        self.settings_page.refresh_status()

    def check_numbers_against_history(self, numbers: Sequence[int]) -> List[Dict[str, Any]]:
        normalized = list(numbers)
        results = []
        for draw in self.stats_manager.winning_data:
            winning_numbers = list(draw.get('numbers', []))
            matches = len(set(normalized) & set(winning_numbers))
            bonus_hit = int(draw.get('bonus', 0)) in normalized
            rank = StrategyEngine([]).rank_ticket(normalized, winning_numbers, int(draw.get('bonus', 0)))
            if rank > 0 or matches >= 2:
                results.append({
                    'label': '과거 회차',
                    'drawNo': draw.get('draw_no'),
                    'matches': f"{matches}{' + 보너스' if bonus_hit else ''}",
                    'rank': rank,
                    'note': ', '.join(str(value) for value in winning_numbers),
                })
        return results[:20]

    def check_ticket(self, ticket: Dict[str, Any]) -> List[Dict[str, Any]]:
        target_draw = self.store.get_winning_draw_by_no(self.stats_manager.winning_data, int(ticket.get('targetDrawNo', 0)))
        if not target_draw:
            return [{'label': '티켓', 'drawNo': ticket.get('targetDrawNo'), 'matches': 0, 'rank': '-', 'note': '아직 결과 없음'}]
        matches = len(set(ticket.get('numbers', [])) & set(target_draw.get('numbers', [])))
        rank = StrategyEngine([]).rank_ticket(ticket.get('numbers', []), target_draw.get('numbers', []), int(target_draw.get('bonus', 0)))
        return [{
            'label': '티켓',
            'drawNo': ticket.get('targetDrawNo'),
            'matches': matches,
            'rank': rank,
            'note': ', '.join(str(value) for value in target_draw.get('numbers', [])),
        }]

    def start_sync(self):
        if self._active_sync_worker and self._active_sync_worker.isRunning():
            return
        worker = LottoSyncWorker(APP_CONFIG['LOTTO_HISTORY_DB'], recent_window=APP_CONFIG['SYNC_RECENT_WINDOW'])
        self._active_sync_worker = worker
        self.settings_page.append_log('동기화를 시작했습니다.')
        worker.finished.connect(self._on_sync_finished)
        worker.error.connect(self._on_sync_error)
        worker.start()

    def _on_sync_finished(self, summary: Dict[str, Any]):
        fetched_records = summary.get('fetched_records', [])
        failed_draws = summary.get('failed_draws', [])
        target_count = int(summary.get('target_count') or 0)
        cancelled = bool(summary.get('cancelled', False))
        inserted = updated = unchanged = invalid = 0
        for record in fetched_records:
            status = self.stats_manager.upsert_winning_data(
                record['draw_no'],
                record['numbers'],
                record['bonus'],
                draw_date=record.get('date'),
                first_prize=record.get('first_prize'),
                first_winners=record.get('first_winners'),
                total_sales=record.get('total_sales'),
            )
            if status == 'inserted':
                inserted += 1
            elif status == 'updated':
                updated += 1
            elif status == 'unchanged':
                unchanged += 1
            else:
                invalid += 1
        now = dt.datetime.now().isoformat()
        latest = self.get_latest_draw_no()
        success_count = inserted + updated + unchanged
        up_to_date = target_count == 0 and not failed_draws and not cancelled
        full_success = (success_count > 0 and not failed_draws and invalid == 0 and not cancelled) or up_to_date
        partial_success = success_count > 0 and (bool(failed_draws) or invalid > 0 or cancelled)
        full_failure = not full_success and not partial_success
        failure_parts = []
        if failed_draws:
            failure_parts.append('실패 회차: ' + ', '.join(str(item) for item in failed_draws[:5]))
        if invalid:
            failure_parts.append(f'저장 실패 {invalid}건')
        if cancelled:
            failure_parts.append('동기화 취소')
        detail_message = ' / '.join(failure_parts)

        sync_meta = {
            **(self.store.state.get('syncMeta') or {}),
            'mode': 'automatic_fallback',
            'currentSource': '기본 자동 동기화',
        }
        if full_success:
            sync_meta.update({
                'lastSuccessAt': now,
                'lastSuccessDrawNo': latest,
                'lastFailureAt': '',
                'lastFailureMessage': '',
                'lastWarningAt': '',
                'lastWarningMessage': '',
            })
            outcome = '성공'
        elif partial_success:
            sync_meta.update({
                'lastSuccessAt': now,
                'lastSuccessDrawNo': latest,
                'lastFailureAt': '',
                'lastFailureMessage': '',
                'lastWarningAt': now,
                'lastWarningMessage': detail_message or '일부 회차를 반영하지 못했습니다.',
            })
            outcome = '부분 성공'
        else:
            sync_meta.update({
                'lastFailureAt': now,
                'lastFailureMessage': detail_message or '동기화 대상 회차를 반영하지 못했습니다.',
            })
            outcome = '실패'
        self.store.state['syncMeta'] = sync_meta
        self.store.save()
        self.refresh_all_views()
        self.settings_page.append_log(f'동기화 {outcome}: inserted={inserted}, updated={updated}, unchanged={unchanged}, invalid={invalid}, failed={len(failed_draws)}')
        self.show_status(f'당첨 데이터 동기화 {outcome}', 4000)

    def _on_sync_error(self, message: str):
        now = dt.datetime.now().isoformat()
        self.store.state['syncMeta'] = {
            **self.store.state['syncMeta'],
            'lastFailureAt': now,
            'lastFailureMessage': message,
        }
        self.store.save()
        self.settings_page.append_log(f'동기화 실패: {message}')
        QMessageBox.warning(self, '동기화 실패', message)

    def closeEvent(self, a0: QCloseEvent | None):
        if a0 is None:
            return
        try:
            encoded_geometry = self.saveGeometry().toBase64().data()
            self.store.state['windowGeometry'] = encoded_geometry.decode('ascii')
            self.store.save()
        finally:
            super().closeEvent(a0)
