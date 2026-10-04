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
    QProgressBar,
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

class SettingsPage(QWidget):
    syncRequested = pyqtSignal()
    fullRepairRequested = pyqtSignal()
    syncCancelRequested = pyqtSignal()

    def __init__(self, app_window: 'LottoApp'):
        super().__init__(app_window)
        self.app_window = app_window
        self._is_refreshing = False
        layout = QVBoxLayout(self)

        self.health_label = QLabel()
        self.health_label.setWordWrap(True)
        self.sync_label = QLabel()
        self.sync_label.setWordWrap(True)
        layout.addWidget(self.health_label)
        layout.addWidget(self.sync_label)

        proxy_group = QGroupBox('인터넷 연결(회사·학교망)')
        proxy_layout = QHBoxLayout(proxy_group)
        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText('필요할 때만 입력 (예: http://127.0.0.1:8080)')
        proxy_layout.addWidget(self.proxy_input, 1)
        self.proxy_save_btn = QPushButton('저장')
        self.proxy_save_btn.clicked.connect(self._save_proxy)
        proxy_layout.addWidget(self.proxy_save_btn)
        layout.addWidget(proxy_group)

        alert_group = QGroupBox('알림 설정')
        alert_layout = QVBoxLayout(alert_group)
        self.enable_in_app_chk = QCheckBox('앱에서 알리기')
        self.enable_in_app_chk.toggled.connect(self._save_alert_prefs)
        alert_layout.addWidget(self.enable_in_app_chk)
        self.notify_new_result_chk = QCheckBox('새 당첨 결과가 나오면 알리기')
        self.notify_new_result_chk.toggled.connect(self._save_alert_prefs)
        alert_layout.addWidget(self.notify_new_result_chk)
        self.system_notification_chk = QCheckBox('PC 알림으로 받기(준비 중)')
        self.system_notification_chk.setEnabled(False)
        alert_layout.addWidget(self.system_notification_chk)
        layout.addWidget(alert_group)

        sync_actions = QHBoxLayout()
        self.sync_btn = QPushButton('최신 정보 가져오기')
        self.sync_btn.clicked.connect(self.syncRequested.emit)
        sync_actions.addWidget(self.sync_btn)
        self.full_repair_btn = QPushButton('빠진 회차 모두 채우기')
        self.full_repair_btn.clicked.connect(self.fullRepairRequested.emit)
        sync_actions.addWidget(self.full_repair_btn)
        self.cancel_btn = QPushButton('가져오기 중단')
        self.cancel_btn.clicked.connect(self.syncCancelRequested.emit)
        sync_actions.addWidget(self.cancel_btn)
        sync_actions.addStretch()
        layout.addLayout(sync_actions)
        self.sync_progress = QProgressBar()
        self.sync_progress.setTextVisible(True)
        layout.addWidget(self.sync_progress)

        self.theme_btn = QPushButton('밝기 바꾸기')
        self.theme_btn.clicked.connect(self.app_window.toggle_theme)
        layout.addWidget(self.theme_btn)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)
        self.set_sync_in_progress(False)

    @staticmethod
    def _data_state_label(availability: Any) -> str:
        return {'full': '준비됨', 'partial': '더 필요함', 'none': '없음'}.get(str(availability or ''), '확인 중')

    def refresh_status(self):
        self._is_refreshing = True
        health = self.app_window.store.state['dataHealth']
        pension_health = self.app_window.store.state.get('pension720DataHealth') or {}
        sync_meta = self.app_window.store.state['syncMeta']
        alert_prefs = self.app_window.store.get_alert_prefs()
        self.health_label.setText(
            "\n".join(
                [
                    f"로또: {self._data_state_label(health.get('availability'))} · 최신 {health.get('latestDrawNo') or '-'}회 · {health.get('message') or '당첨 정보를 확인하는 중...'}",
                    f"연금복권: {self._data_state_label(pension_health.get('availability'))} · 최신 {pension_health.get('latestDrawNo') or '-'}회 · {pension_health.get('message') or '연금복권 정보를 확인하는 중...'}",
                ]
            )
        )
        last_success = sync_meta.get('lastSuccessAt') or '-'
        last_success_draw = sync_meta.get('lastSuccessDrawNo') or 0
        last_notice = sync_meta.get('lastWarningMessage') or sync_meta.get('lastFailureMessage') or '-'
        self.sync_label.setText(
            "\n".join(
                [
                    f"마지막으로 가져온 정보: {last_success}" + (f" ({last_success_draw}회)" if last_success_draw else ''),
                    f"최근 안내: {last_notice}",
                ]
            )
        )
        self.proxy_input.setText(str(self.app_window.store.state.get('proxyUrl') or ''))
        self.enable_in_app_chk.setChecked(bool(alert_prefs.get('enableInApp')))
        self.notify_new_result_chk.setChecked(bool(alert_prefs.get('notifyOnNewResult')))
        self.system_notification_chk.setChecked(bool(alert_prefs.get('enableSystemNotification')))
        self._is_refreshing = False

    def append_log(self, message: str):
        self.log.append(message)

    def set_sync_in_progress(self, busy: bool):
        self.sync_btn.setEnabled(not busy)
        self.full_repair_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        if busy:
            self.sync_progress.setValue(0)
            self.sync_progress.setVisible(True)
        else:
            self.sync_progress.setVisible(False)

    def set_sync_progress(self, done: int, total: int) -> None:
        self.sync_progress.setVisible(True)
        self.sync_progress.setMaximum(max(1, int(total)))
        self.sync_progress.setValue(max(0, int(done)))

    def _save_proxy(self):
        self.app_window.save_proxy_url(self.proxy_input.text())

    def _save_alert_prefs(self):
        if self._is_refreshing:
            return
        self.app_window.update_alert_preferences(
            enable_in_app=self.enable_in_app_chk.isChecked(),
            notify_on_new_result=self.notify_new_result_chk.isChecked(),
        )

