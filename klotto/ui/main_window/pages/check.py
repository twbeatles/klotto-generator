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
        button_row.addStretch()
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


