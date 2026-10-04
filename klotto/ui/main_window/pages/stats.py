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

class StatsPage(QWidget):
    def __init__(self, app_window: 'LottoApp'):
        super().__init__(app_window)
        self.app_window = app_window
        layout = QVBoxLayout(self)
        self.summary_label = QLabel('통계를 불러오는 중...')
        layout.addWidget(self.summary_label)
        self.hot_table = QTableWidget(0, 2)
        self.hot_table.setHorizontalHeaderLabels(['자주 나온 번호', '나온 횟수'])
        self.cold_table = QTableWidget(0, 2)
        self.cold_table.setHorizontalHeaderLabels(['오래 안 나온 번호', '나온 횟수'])
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
        availability = str(self.app_window.store.state['dataHealth'].get('availability') or 'none')
        extra = '' if availability == 'full' else ' · 빠진 회차가 있어요. 설정·최신 정보에서 가져오세요.'
        self.summary_label.setText(f"총 {total_draws}개 회차 · 최신 {latest_draw}회까지 준비됨{extra}")
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


