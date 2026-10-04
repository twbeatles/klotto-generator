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
            'pension720Tickets': ['조', '번호', '대상 회차', '출처', '메모'],
            'pension720Campaigns': ['이름', '시작', '회차 수', '회차당', '저장'],
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
        self._fill_table(self.tables['pension720Tickets'], [[str(item.get('group', '')), str(item.get('number', '')), str(item.get('targetDrawNo') or ''), str(item.get('source', '')), str(item.get('memo', ''))] for item in self.app_window.store.state['pension720Tickets']])
        self._fill_table(self.tables['pension720Campaigns'], [[item.get('name', ''), str(item.get('startDrawNo', '')), str(item.get('weeks', '')), str(item.get('setsPerDraw', '')), str(self.app_window.store.count_pension720_tickets_by_campaign_id(str(item.get('id') or '')))] for item in self.app_window.store.state['pension720Campaigns']])

    def _fill_table(self, table: QTableWidget, rows: Sequence[Sequence[str]]):
        table.setRowCount(0)
        for row_values in rows:
            row = table.rowCount()
            table.insertRow(row)
            for col, value in enumerate(row_values):
                table.setItem(row, col, QTableWidgetItem(str(value)))

    def current_dataset_name(self) -> str:
        names = ['favorites', 'history', 'tickets', 'campaigns', 'pension720Tickets', 'pension720Campaigns']
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
        elif dataset == 'pension720Tickets':
            ticket = self.app_window.store.state['pension720Tickets'][row]
            removed = bool(self.app_window.store.remove_pension720_ticket(str(ticket.get('id') or '')))
        elif dataset == 'pension720Campaigns':
            campaign = self.app_window.store.state['pension720Campaigns'][row]
            result = self.app_window.store.remove_pension720_campaign(str(campaign.get('id') or ''), cascade_tickets=True)
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
        elif dataset == 'pension720Tickets':
            removed = self.app_window.store.clear_pension720_tickets()
        elif dataset == 'pension720Campaigns':
            result = self.app_window.store.clear_pension720_campaigns(cascade_tickets=True)
            removed = int(result.get('removedCampaigns', 0))
        self.app_window.refresh_all_views()
        self.app_window.show_status(f'{dataset} 정리 완료 ({removed})', 4000)

    def _ticket_status(self, ticket: Dict[str, Any]) -> str:
        checked = ticket.get('checked')
        if not checked:
            return '예정'
        return '당첨' if int(checked.get('rank', 0)) > 0 else '미당첨'

    def export_backup(self):
        timestamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        prefix = str(APP_CONFIG.get('BACKUP_EXPORT_PREFIX') or 'lotto_pension_pro_backup_v5')
        filepath, _ = QFileDialog.getSaveFileName(self, '백업 저장', f'{prefix}_{timestamp}.json', 'JSON 파일 (*.json)')
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
        choice, accepted = QInputDialog.getItem(
            self,
            '백업 가져오기',
            '가져오기 방식',
            ['merge 방식으로 불러오기(권장)', '덮어쓰기로 불러오기'],
            0,
            False,
        )
        if not accepted:
            return
        mode = 'overwrite' if str(choice).startswith('덮어쓰기') else 'merge'
        timestamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        snapshot = Path(self.app_window.store.state_file).with_name(f'app_state.preimport-{timestamp}.json')
        DataExporter.export_any_json(self.app_window.store.export_backup_payload(), str(snapshot))
        self.app_window.store.import_backup_payload(payload, mode=mode, winning_data=self.app_window.stats_manager.winning_data)
        self.app_window.refresh_all_views()
        self.app_window.show_status(f'백업을 {mode} 방식으로 불러왔습니다 (가져오기 전 상태: {snapshot.name}).', 4000)

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


