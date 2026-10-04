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

class BacktestPage(QWidget):
    def __init__(self, app_window: 'LottoApp'):
        super().__init__(app_window)
        self.app_window = app_window
        self._task: Optional[TaskThread] = None
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.strategy_editor = StrategyRequestEditor('backtest', '시험에 쓸 기준 방식', store=self.app_window.store)
        self.strategy_editor.strategiesChanged.connect(lambda: self._populate_strategy_list(self._selected_strategy_ids()))
        self.strategy_editor.presetApplied.connect(self._on_preset_applied)
        top.addWidget(self.strategy_editor, 2)

        side = QGroupBox('지난 결과로 시험하기')
        side_form = QFormLayout(side)
        self.start_draw_spin = QSpinBox()
        self.start_draw_spin.setRange(1, 9999)
        side_form.addRow('시작 회차', self.start_draw_spin)
        self.end_draw_spin = QSpinBox()
        self.end_draw_spin.setRange(1, 9999)
        side_form.addRow('마지막 회차', self.end_draw_spin)
        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, 20)
        self.qty_spin.setValue(5)
        side_form.addRow('회차마다 살 개수', self.qty_spin)
        self.strategy_list = QListWidget()
        self.strategy_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        side_form.addRow('비교할 방식', self.strategy_list)
        self.run_btn = QPushButton('시험 시작')
        self.run_btn.clicked.connect(self.run_backtest)
        side_form.addRow(self.run_btn)
        top.addWidget(side, 1)
        layout.addLayout(top)

        self.result_table = QTableWidget(0, 7)
        self.result_table.setHorizontalHeaderLabels(['방식', '수익률', '맞힌 비율', '쓴 회차', '산 개수', '받은 상금', '쓴 금액'])
        layout.addWidget(self.result_table, 1)
        self.hydrate_defaults()

    def hydrate_defaults(self):
        pref = self.app_window.store.get_strategy_pref('backtest')
        self.strategy_editor.apply_request(pref)
        latest = self.app_window.get_latest_draw_no()
        self.start_draw_spin.setValue(max(1, latest - 30))
        self.end_draw_spin.setValue(latest)
        selected_strategy = str(pref.get('strategyId') or self.strategy_editor.strategy_combo.currentData() or '')
        self._populate_strategy_list({selected_strategy} if selected_strategy else set())
        self.update_data_gate()

    def refresh_defaults(self):
        self.hydrate_defaults()

    def refresh_view_state(self):
        self._populate_strategy_list(self._selected_strategy_ids())
        self.update_data_gate()

    def _selected_strategy_ids(self) -> set[str]:
        selected: set[str] = set()
        for item in self.strategy_list.selectedItems():
            strategy_id = str(item.data(Qt.ItemDataRole.UserRole) or '').strip()
            if strategy_id:
                selected.add(strategy_id)
        return selected

    def _populate_strategy_list(self, selected_ids: Optional[set[str]] = None):
        preserved = selected_ids if selected_ids is not None else self._selected_strategy_ids()
        self.strategy_list.clear()
        for index in range(self.strategy_editor.strategy_combo.count()):
            label = self.strategy_editor.strategy_combo.itemText(index)
            strategy_id = str(self.strategy_editor.strategy_combo.itemData(index) or '')
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, strategy_id)
            self.strategy_list.addItem(item)
            if strategy_id and strategy_id in preserved:
                item.setSelected(True)
        if not self.strategy_list.selectedItems() and self.strategy_list.count() > 0:
            first_item = self.strategy_list.item(0)
            if first_item is not None:
                first_item.setSelected(True)

    def _on_preset_applied(self, _preset: Dict[str, Any]):
        request = self.strategy_editor.build_request()
        self.app_window.store.set_strategy_pref('backtest', request)
        selected_strategy = str(request.get('strategyId') or '')
        self._populate_strategy_list({selected_strategy} if selected_strategy else self._selected_strategy_ids())

    def update_data_gate(self):
        allowed = self.app_window.is_data_health_full()
        self.strategy_editor.setEnabled(allowed)
        self.strategy_list.setEnabled(allowed)
        self.run_btn.setEnabled(allowed)
        self.run_btn.setToolTip('' if allowed else '당첨 정보를 모두 가져온 뒤에 이용할 수 있어요. 설정·최신 정보에서 최신 정보를 가져오세요.')

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
        thread.errorOccurred.connect(lambda message: QMessageBox.warning(self, '시험 실패', message))
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
        self.app_window.show_status('지난 결과 시험이 끝났어요.', 4000)


