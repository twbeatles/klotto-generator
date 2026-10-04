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
from klotto.data.store.campaigns import campaign_size_error
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

class Pension720Page(QWidget):
    def __init__(self, app_window: 'LottoApp'):
        super().__init__(app_window)
        self.app_window = app_window
        self.pension720_stats: List[Dict[str, Any]] = []
        self.last_recommendations: List[Dict[str, Any]] = []
        self.last_request: Dict[str, Any] = self.app_window.store.get_strategy_pref('pension720')
        self._task: Optional[TaskThread] = None
        self._setup_ui()
        self.reload_static_data()
        self.apply_saved_strategy_pref()
        self.reset_campaign_defaults(force=True)
        self.refresh_view_state()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        header = QLabel('연금복권720+')
        header.setFont(QFont('Segoe UI', 16, QFont.Weight.Bold))
        layout.addWidget(header)

        status_group = QGroupBox('연금복권 당첨 정보')
        status_layout = QVBoxLayout(status_group)
        status_row = QHBoxLayout()
        self.status_label = QLabel('연금복권 정보를 확인하는 중...')
        self.latest_label = QLabel('-')
        self.refresh_btn = QPushButton('최신 정보 확인')
        self.refresh_btn.clicked.connect(self.refresh_official_data)
        status_row.addWidget(self.status_label, 2)
        status_row.addWidget(self.latest_label, 1)
        status_row.addWidget(self.refresh_btn)
        status_layout.addLayout(status_row)
        stats_row = QHBoxLayout()
        self.group_stats_table = QTableWidget(0, 3)
        self.group_stats_table.setHorizontalHeaderLabels(['조', '나온 횟수', '흐름'])
        self.digit_stats_table = QTableWidget(0, 4)
        self.digit_stats_table.setHorizontalHeaderLabels(['자리', '1순위', '2순위', '3순위'])
        stats_row.addWidget(self.group_stats_table)
        stats_row.addWidget(self.digit_stats_table)
        status_layout.addLayout(stats_row)
        layout.addWidget(status_group)

        top = QHBoxLayout()
        strategy_group = QGroupBox('번호 추천 설정')
        form = QFormLayout(strategy_group)
        preset_row = QHBoxLayout()
        self.preset_combo = QComboBox()
        preset_row.addWidget(self.preset_combo, 1)
        self.load_preset_btn = QPushButton('불러오기')
        self.load_preset_btn.clicked.connect(self.load_selected_preset)
        preset_row.addWidget(self.load_preset_btn)
        self.save_preset_btn = QPushButton('저장')
        self.save_preset_btn.clicked.connect(self.save_current_preset)
        preset_row.addWidget(self.save_preset_btn)
        self.delete_preset_btn = QPushButton('삭제')
        self.delete_preset_btn.clicked.connect(self.delete_selected_preset)
        preset_row.addWidget(self.delete_preset_btn)
        form.addRow('저장된 설정', preset_row)

        self.experimental_chk = QCheckBox('실험 중인 방식도 보기')
        self.experimental_chk.toggled.connect(self.populate_strategy_select)
        form.addRow(self.experimental_chk)

        self.strategy_combo = QComboBox()
        form.addRow('추천 방식', self.strategy_combo)

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, APP_CONFIG['MAX_SETS'])
        self.count_spin.setValue(5)
        form.addRow('받을 개수', self.count_spin)

        self.analysis_preset_combo = QComboBox()
        self.analysis_preset_combo.addItem('빠르게', 'fast')
        self.analysis_preset_combo.addItem('보통', 'basic')
        self.analysis_preset_combo.addItem('꼼꼼하게', 'precise')
        self.analysis_preset_combo.addItem('직접 정하기', 'custom')
        self.analysis_preset_combo.currentIndexChanged.connect(self.apply_analysis_preset_from_combo)
        form.addRow('얼마나 꼼꼼히 볼지', self.analysis_preset_combo)

        self.lookback_spin = QSpinBox()
        self.lookback_spin.setRange(1, 300)
        self.lookback_spin.setValue(40)
        form.addRow('참고할 최근 회차 수', self.lookback_spin)

        self.pool_spin = QSpinBox()
        self.pool_spin.setRange(20, 800)
        self.pool_spin.setSingleStep(10)
        self.pool_spin.setValue(140)
        form.addRow('검토할 후보 개수', self.pool_spin)

        self.seed_edit = QLineEdit()
        self.seed_edit.setPlaceholderText('비워두면 매번 다르게')
        form.addRow('고정값', self.seed_edit)

        self.target_draw_spin = QSpinBox()
        self.target_draw_spin.setRange(1, 9999)
        form.addRow('저장할 회차', self.target_draw_spin)

        self.groups_edit = QLineEdit()
        self.groups_edit.setPlaceholderText('원하는 조만 (예: 1,2,5)')
        form.addRow('원하는 조(1~5)', self.groups_edit)

        self.fixed_digits_edit = QLineEdit()
        self.fixed_digits_edit.setPlaceholderText('예: 첫째 자리는 0, 여섯째 자리는 7 → 1=0, 6=7')
        form.addRow('정해둘 자리 숫자', self.fixed_digits_edit)

        self.excluded_digits_edit = QLineEdit()
        self.excluded_digits_edit.setPlaceholderText('예: 둘째 자리에서 9, 8 빼기 → 2=9,8')
        form.addRow('빼고 싶은 자리 숫자', self.excluded_digits_edit)

        self.sum_min_spin, self.sum_max_spin = self._pair_spins(0, 54)
        form.addRow('여섯 자리 합', self._pair_widget(self.sum_min_spin, self.sum_max_spin))
        self.odd_min_spin, self.odd_max_spin = self._pair_spins(0, 6)
        form.addRow('홀수인 자리 수', self._pair_widget(self.odd_min_spin, self.odd_max_spin))
        self.high_min_spin, self.high_max_spin = self._pair_spins(0, 6)
        form.addRow('5 이상인 자리 수', self._pair_widget(self.high_min_spin, self.high_max_spin))

        self.unique_spin = QSpinBox()
        self.unique_spin.setRange(-1, 6)
        self.unique_spin.setSpecialValueText('사용 안 함')
        self.unique_spin.setValue(-1)
        form.addRow('서로 다른 숫자 최소 개수', self.unique_spin)

        self.max_same_spin = QSpinBox()
        self.max_same_spin.setRange(-1, 6)
        self.max_same_spin.setSpecialValueText('사용 안 함')
        self.max_same_spin.setValue(-1)
        form.addRow('같은 숫자 최대 개수', self.max_same_spin)

        self.recommend_btn = QPushButton('번호 추천받기')
        self.recommend_btn.clicked.connect(self.run_recommendation)
        form.addRow(self.recommend_btn)
        top.addWidget(strategy_group, 2)

        campaign_group = QGroupBox('묶음 구매')
        campaign_form = QFormLayout(campaign_group)
        self.campaign_start_spin = QSpinBox()
        self.campaign_start_spin.setRange(1, 9999)
        campaign_form.addRow('시작 회차', self.campaign_start_spin)
        self.campaign_weeks_spin = QSpinBox()
        self.campaign_weeks_spin.setRange(1, APP_CONFIG['MAX_CAMPAIGN_WEEKS'])
        self.campaign_weeks_spin.setValue(4)
        campaign_form.addRow('이어서 할 회차 수', self.campaign_weeks_spin)
        self.campaign_sets_spin = QSpinBox()
        self.campaign_sets_spin.setRange(1, APP_CONFIG['MAX_CAMPAIGN_SETS_PER_WEEK'])
        self.campaign_sets_spin.setValue(3)
        campaign_form.addRow('회차마다 개수', self.campaign_sets_spin)
        self.campaign_btn = QPushButton('묶음으로 만들기')
        self.campaign_btn.clicked.connect(self.run_campaign_recommendation)
        campaign_form.addRow(self.campaign_btn)
        self.reset_campaign_btn = QPushButton('기본값으로 되돌리기')
        self.reset_campaign_btn.clicked.connect(lambda: self.reset_campaign_defaults(force=True))
        campaign_form.addRow(self.reset_campaign_btn)
        top.addWidget(campaign_group, 1)
        layout.addLayout(top)

        self.recommendations_table = QTableWidget(0, 6)
        self.recommendations_table.setHorizontalHeaderLabels(['순서', '조', '번호', '추천도', '방식', '이유'])
        self.recommendations_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.recommendations_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.recommendations_table, 1)

        recommend_actions = QHBoxLayout()
        self.save_selected_btn = QPushButton('고른 번호 저장')
        self.save_selected_btn.clicked.connect(self.save_selected_recommendation)
        recommend_actions.addWidget(self.save_selected_btn)
        self.save_expansion_btn = QPushButton('같은 번호 5개 조 모두 저장')
        self.save_expansion_btn.clicked.connect(self.save_selected_expansion)
        recommend_actions.addWidget(self.save_expansion_btn)
        recommend_actions.addStretch()
        layout.addLayout(recommend_actions)

        saved_group = QGroupBox('저장한 번호 확인하기')
        saved_layout = QVBoxLayout(saved_group)
        saved_actions = QHBoxLayout()
        self.saved_summary_label = QLabel('0개 저장됨')
        saved_actions.addWidget(self.saved_summary_label)
        self.copy_saved_btn = QPushButton('복사하기')
        self.copy_saved_btn.clicked.connect(self.copy_saved_tickets)
        saved_actions.addWidget(self.copy_saved_btn)
        self.export_csv_btn = QPushButton('파일로 저장')
        self.export_csv_btn.clicked.connect(self.export_saved_tickets_csv)
        saved_actions.addWidget(self.export_csv_btn)
        self.clear_tickets_btn = QPushButton('모두 지우기')
        self.clear_tickets_btn.clicked.connect(self.clear_saved_tickets)
        saved_actions.addWidget(self.clear_tickets_btn)
        self.check_latest_btn = QPushButton('당첨 확인하기')
        self.check_latest_btn.clicked.connect(self.run_saved_ticket_check)
        saved_actions.addWidget(self.check_latest_btn)
        saved_actions.addStretch()
        saved_layout.addLayout(saved_actions)

        saved_tables = QHBoxLayout()
        self.saved_table = QTableWidget(0, 7)
        self.saved_table.setHorizontalHeaderLabels(['조', '번호', '구매 회차', '가져온 곳', '메모', '저장한 날', '상태'])
        self.saved_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.saved_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        saved_tables.addWidget(self.saved_table)
        self.campaign_table = QTableWidget(0, 5)
        self.campaign_table.setHorizontalHeaderLabels(['이름', '시작 회차', '회차 수', '회차마다', '저장된 개수'])
        self.campaign_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.campaign_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        saved_tables.addWidget(self.campaign_table)
        saved_layout.addLayout(saved_tables)

        self.check_table = QTableWidget(0, 5)
        self.check_table.setHorizontalHeaderLabels(['번호', '상태', '회차', '결과', '상금'])
        self.check_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        saved_layout.addWidget(self.check_table)
        layout.addWidget(saved_group)

        self.populate_strategy_select()
        self.reload_presets()

    def _pair_spins(self, min_value: int, max_value: int) -> tuple[QSpinBox, QSpinBox]:
        left = QSpinBox()
        right = QSpinBox()
        for spin in (left, right):
            spin.setRange(-1, max_value)
            spin.setSpecialValueText('사용 안 함')
            spin.setValue(-1)
        return left, right

    def _pair_widget(self, left: QSpinBox, right: QSpinBox) -> QWidget:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(left)
        row.addWidget(QLabel('~'))
        row.addWidget(right)
        return widget

    def reload_static_data(self):
        self.pension720_stats = load_pension720_static_data()
        if self.pension720_stats:
            latest = self.pension720_stats[0]
            self.app_window.store.set_pension720_data_health(
                availability='full',
                source='static',
                latestDrawNo=int(latest.get('draw_no', 0)),
                message='기본 포함 연금복권 데이터를 사용 중입니다.',
                updatedAt=dt.datetime.now().isoformat(),
            )

    def populate_strategy_select(self):
        current = str(self.strategy_combo.currentData() or 'mixed_balance')
        self.strategy_combo.blockSignals(True)
        self.strategy_combo.clear()
        for meta in list_pension720_strategies(include_experimental=self.experimental_chk.isChecked()):
            summary = str(meta.get('summary') or '').strip()
            label = f"{meta['label']} — {summary}" if summary else str(meta['label'])
            self.strategy_combo.addItem(label, meta['id'])
        resolved = resolve_pension720_strategy_id(current)
        index = self.strategy_combo.findData(resolved)
        self.strategy_combo.setCurrentIndex(index if index >= 0 else 0)
        self.strategy_combo.blockSignals(False)

    def reload_presets(self):
        current = str(self.preset_combo.currentData() or '')
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem('저장된 설정 선택', '')
        for preset in self.app_window.store.get_strategy_presets('pension720'):
            self.preset_combo.addItem(str(preset.get('name') or '이름 없는 설정'), str(preset.get('id') or ''))
        index = self.preset_combo.findData(current)
        self.preset_combo.setCurrentIndex(index if index >= 0 else 0)
        self.preset_combo.blockSignals(False)
        self.delete_preset_btn.setEnabled(bool(self._get_selected_preset()))

    def _get_selected_preset(self) -> Optional[Dict[str, Any]]:
        preset_id = str(self.preset_combo.currentData() or '').strip()
        if not preset_id:
            return None
        for preset in self.app_window.store.get_strategy_presets('pension720'):
            if str(preset.get('id') or '') == preset_id:
                return preset
        return None

    def apply_saved_strategy_pref(self):
        self.apply_strategy_request(self.app_window.store.get_strategy_pref('pension720'))

    def apply_analysis_preset_from_combo(self, *_args: Any):
        preset = str(self.analysis_preset_combo.currentData() or 'custom')
        if preset == 'fast':
            self.lookback_spin.setValue(20)
            self.pool_spin.setValue(80)
        elif preset == 'basic':
            self.lookback_spin.setValue(40)
            self.pool_spin.setValue(140)
        elif preset == 'precise':
            self.lookback_spin.setValue(80)
            self.pool_spin.setValue(240)

    def _read_pair(self, left: QSpinBox, right: QSpinBox) -> Optional[List[int]]:
        if left.value() < 0 or right.value() < 0:
            return None
        return sorted([left.value(), right.value()])

    def _parse_groups(self) -> Optional[List[int]]:
        text = self.groups_edit.text().strip()
        if not text:
            return None
        groups = sorted({int(value) for value in text.replace(';', ',').split(',') if value.strip().isdigit() and 1 <= int(value.strip()) <= 5})
        return groups or None

    def _parse_fixed_digits(self) -> Optional[List[Optional[int]]]:
        text = self.fixed_digits_edit.text().strip()
        if not text:
            return None
        out: List[Optional[int]] = [None] * 6
        found = False
        import re

        for match in re.finditer(r'([1-6])\s*[:=]\s*([0-9])', text):
            out[int(match.group(1)) - 1] = int(match.group(2))
            found = True
        return out if found else None

    def _parse_excluded_digits(self) -> Optional[List[List[int]]]:
        text = self.excluded_digits_edit.text().strip()
        if not text:
            return None
        out: List[List[int]] = [[] for _ in range(6)]
        found = False
        import re

        for segment in re.split(r'[;|/]+', text):
            match = re.search(r'([1-6])\s*[:=]\s*([0-9,\s]+)', segment)
            if not match:
                continue
            pos = int(match.group(1)) - 1
            digits = sorted({int(value) for value in re.split(r'[^0-9]+', match.group(2)) if value != ''})
            digits = [digit for digit in digits if 0 <= digit <= 9]
            if digits:
                out[pos] = digits
                found = True
        return out if found else None

    def build_request(self) -> Dict[str, Any]:
        seed_text = self.seed_edit.text().strip()
        seed = int(seed_text) if seed_text and seed_text.lstrip('-').isdigit() and int(seed_text) > 0 else None
        return self.app_window.store.normalize_pension720_strategy_request(
            {
                'strategyId': str(self.strategy_combo.currentData() or 'mixed_balance'),
                'params': {
                    'seed': seed,
                    'lookbackWindow': self.lookback_spin.value(),
                    'candidatePoolSize': self.pool_spin.value(),
                },
                'filters': {
                    'groups': self._parse_groups(),
                    'fixedDigits': self._parse_fixed_digits(),
                    'excludedDigitsByPosition': self._parse_excluded_digits(),
                    'digitSumRange': self._read_pair(self.sum_min_spin, self.sum_max_spin),
                    'oddDigitRange': self._read_pair(self.odd_min_spin, self.odd_max_spin),
                    'highDigitRange': self._read_pair(self.high_min_spin, self.high_max_spin),
                    'uniqueDigitMin': None if self.unique_spin.value() < 0 else self.unique_spin.value(),
                    'maxSameDigit': None if self.max_same_spin.value() < 0 else self.max_same_spin.value(),
                },
            }
        )

    def apply_strategy_request(self, request: Dict[str, Any]):
        normalized = self.app_window.store.normalize_pension720_strategy_request(request)
        strategy_id = str(normalized.get('strategyId') or 'mixed_balance')
        index = self.strategy_combo.findData(strategy_id)
        if index >= 0:
            self.strategy_combo.setCurrentIndex(index)
        params = normalized.get('params') or {}
        filters = normalized.get('filters') or {}
        self.seed_edit.setText('' if params.get('seed') is None else str(params.get('seed')))
        self.lookback_spin.setValue(int(params.get('lookbackWindow') or 40))
        self.pool_spin.setValue(int(params.get('candidatePoolSize') or 140))
        self.groups_edit.setText(','.join(str(item) for item in (filters.get('groups') or [])))
        self.fixed_digits_edit.setText(self._format_fixed_digits(filters.get('fixedDigits')))
        self.excluded_digits_edit.setText(self._format_excluded_digits(filters.get('excludedDigitsByPosition')))
        self._apply_pair(self.sum_min_spin, self.sum_max_spin, filters.get('digitSumRange'))
        self._apply_pair(self.odd_min_spin, self.odd_max_spin, filters.get('oddDigitRange'))
        self._apply_pair(self.high_min_spin, self.high_max_spin, filters.get('highDigitRange'))
        self.unique_spin.setValue(-1 if filters.get('uniqueDigitMin') is None else int(filters['uniqueDigitMin']))
        self.max_same_spin.setValue(-1 if filters.get('maxSameDigit') is None else int(filters['maxSameDigit']))

    def _apply_pair(self, left: QSpinBox, right: QSpinBox, value: Any):
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            left.setValue(int(value[0]))
            right.setValue(int(value[1]))
        else:
            left.setValue(-1)
            right.setValue(-1)

    def _format_fixed_digits(self, value: Any) -> str:
        if not isinstance(value, list):
            return ''
        return ', '.join(f'{index + 1}={digit}' for index, digit in enumerate(value[:6]) if digit is not None)

    def _format_excluded_digits(self, value: Any) -> str:
        if not isinstance(value, list):
            return ''
        return '; '.join(f"{index + 1}={','.join(str(digit) for digit in digits)}" for index, digits in enumerate(value[:6]) if digits)

    def save_current_preset(self):
        name, ok = QInputDialog.getText(self, '연금복권 설정 저장', '설정 이름')
        cleaned = name.strip()
        if not ok or not cleaned:
            return
        preset = self.app_window.store.save_strategy_preset('pension720', cleaned, self.build_request())
        if not preset:
            QMessageBox.warning(self, '설정 저장', '설정을 저장할 수 없습니다.')
            return
        self.reload_presets()
        index = self.preset_combo.findData(str(preset.get('id') or ''))
        self.preset_combo.setCurrentIndex(index if index >= 0 else 0)

    def load_selected_preset(self):
        preset = self._get_selected_preset()
        if not preset:
            return
        self.apply_strategy_request(preset.get('request') or {})

    def delete_selected_preset(self):
        preset = self._get_selected_preset()
        if not preset:
            return
        result = QMessageBox.question(self, '설정 삭제', f"'{preset.get('name')}' 설정을 삭제할까요?")
        if result != QMessageBox.StandardButton.Yes:
            return
        if self.app_window.store.delete_strategy_preset(str(preset.get('id') or '')):
            self.reload_presets()

    def get_suggested_next_draw_no(self) -> int:
        return int(self.pension720_stats[0].get('draw_no', 0)) + 1 if self.pension720_stats else 1

    def reset_campaign_defaults(self, *, force: bool = True):
        next_draw = self.get_suggested_next_draw_no()
        if force or self.campaign_start_spin.value() <= 1:
            self.campaign_start_spin.setValue(next_draw)
        if force or self.target_draw_spin.value() <= 1:
            self.target_draw_spin.setValue(next_draw)
        if force:
            self.campaign_weeks_spin.setValue(4)
            self.campaign_sets_spin.setValue(3)

    def refresh_official_data(self):
        proxy_url = str(self.app_window.store.state.get('proxyUrl') or '')

        def task() -> List[Dict[str, Any]]:
            return fetch_pension720_official_stats(proxy_url=proxy_url)

        self.refresh_btn.setEnabled(False)
        thread = TaskThread(task, self)
        self._task = thread
        thread.resultReady.connect(self._on_official_data_ready)
        thread.errorOccurred.connect(self._on_official_data_error)
        thread.finished.connect(lambda: self.refresh_btn.setEnabled(True))
        thread.start()

    def _settle_saved_pension_tickets(self) -> int:
        if not self.pension720_stats:
            return 0
        return self.app_window.store.settle_pension720_tickets_if_possible(
            self.app_window.store.state['pension720Tickets'], self.pension720_stats
        )

    def _on_official_data_ready(self, rows: List[Dict[str, Any]]):
        if rows:
            self.pension720_stats = rows
            latest = rows[0]
            self.app_window.store.set_pension720_data_health(
                availability='full',
                source='official',
                latestDrawNo=int(latest.get('draw_no', 0)),
                message='동행복권 공식 연금복권 데이터를 사용 중입니다.',
                updatedAt=dt.datetime.now().isoformat(),
            )
            self._settle_saved_pension_tickets()
            self.reset_campaign_defaults(force=False)
        self.refresh_view_state()
        self.app_window.show_status('연금복권 최신 정보를 확인했어요.' if rows else '연금복권 정보를 확인하지 못했어요.', 4000)

    def _on_official_data_error(self, message: str):
        self.app_window.store.set_pension720_data_health(
            availability='full' if self.pension720_stats else 'none',
            source='static' if self.pension720_stats else 'none',
            latestDrawNo=int(self.pension720_stats[0].get('draw_no', 0)) if self.pension720_stats else 0,
            message=f'최신 정보 확인 실패: {message}'[:240],
            updatedAt=dt.datetime.now().isoformat(),
        )
        self.refresh_view_state()
        QMessageBox.warning(self, '최신 정보 확인', message)

    def refresh_view_state(self):
        self.render_status()
        self.render_stats()
        self.render_recommendations()
        self.render_saved_tables()
        self.update_data_gate()

    def render_status(self):
        health = self.app_window.store.state.get('pension720DataHealth') or {}
        self.status_label.setText(str(health.get('message') or '연금복권 정보를 준비하는 중...'))
        latest = self.pension720_stats[0] if self.pension720_stats else None
        if latest:
            self.latest_label.setText(f"{latest.get('draw_no')}회 {latest.get('date')} | {latest.get('group')}조 {latest.get('number')} / 보너스 {latest.get('bonus_number')}")
        else:
            self.latest_label.setText('-')

    def render_stats(self):
        self.group_stats_table.setRowCount(0)
        self.digit_stats_table.setRowCount(0)
        if not self.pension720_stats:
            return
        summary = Pension720Engine(self.pension720_stats).get_summary()
        for item in sorted(summary.get('topGroups', []), key=lambda row: int(row.get('group', 0))):
            row = self.group_stats_table.rowCount()
            self.group_stats_table.insertRow(row)
            self.group_stats_table.setItem(row, 0, QTableWidgetItem(f"{item.get('group')}조"))
            self.group_stats_table.setItem(row, 1, QTableWidgetItem(str(item.get('rawCount') or item.get('count') or 0)))
            self.group_stats_table.setItem(row, 2, QTableWidgetItem(f"{float(item.get('score') or 0):.2f}"))
        analysis = Pension720Engine(self.pension720_stats).analysis
        for pos, weights in enumerate(analysis.get('positionStats', []), start=1):
            top_digits = sorted([(digit, weight) for digit, weight in enumerate(weights)], key=lambda item: item[1], reverse=True)[:3]
            row = self.digit_stats_table.rowCount()
            self.digit_stats_table.insertRow(row)
            self.digit_stats_table.setItem(row, 0, QTableWidgetItem(f'{pos}번째 자리'))
            for col, (digit, weight) in enumerate(top_digits, start=1):
                self.digit_stats_table.setItem(row, col, QTableWidgetItem(f'{digit} ({int(round(float(weight)))}번)'))

    def update_data_gate(self):
        has_stats = bool(self.pension720_stats)
        has_recommendations = bool(self.last_recommendations)
        has_tickets = bool(self.app_window.store.state['pension720Tickets'])
        self.recommend_btn.setEnabled(has_stats)
        self.campaign_btn.setEnabled(has_stats)
        self.save_selected_btn.setEnabled(has_recommendations)
        self.save_expansion_btn.setEnabled(has_recommendations)
        self.copy_saved_btn.setEnabled(has_tickets)
        self.export_csv_btn.setEnabled(has_tickets)
        self.clear_tickets_btn.setEnabled(has_tickets)
        self.check_latest_btn.setEnabled(has_tickets and has_stats)

    def run_recommendation(self):
        if not self.pension720_stats:
            QMessageBox.warning(self, '연금복권 추천', '연금복권 정보가 없습니다. [최신 정보 확인]을 먼저 눌러주세요.')
            return
        request = self.build_request()
        self.app_window.store.set_strategy_pref('pension720', request)
        self.last_request = request

        def task() -> List[Dict[str, Any]]:
            return Pension720Engine(self.pension720_stats).recommend({'setCount': self.count_spin.value(), 'request': request})

        self.recommend_btn.setEnabled(False)
        thread = TaskThread(task, self)
        self._task = thread
        thread.resultReady.connect(self._on_recommendations_ready)
        thread.errorOccurred.connect(lambda message: QMessageBox.warning(self, '추천 실패', message))
        thread.finished.connect(lambda: self.update_data_gate())
        thread.start()

    def _on_recommendations_ready(self, rows: List[Dict[str, Any]]):
        self.last_recommendations = list(rows)
        self.render_recommendations()
        self.app_window.show_status(f'연금복권 번호 {len(rows)}개를 추천했어요.', 4000)

    def render_recommendations(self):
        self.recommendations_table.setRowCount(0)
        for index, item in enumerate(self.last_recommendations, start=1):
            row = self.recommendations_table.rowCount()
            self.recommendations_table.insertRow(row)
            values = [
                str(index),
                f"{item.get('group')}조",
                str(item.get('number') or ''),
                f"{float(item.get('score') or 0):.2f}",
                str(item.get('strategyLabel') or item.get('strategyId') or ''),
                ' · '.join(str(reason) for reason in item.get('reasons', [])[:3]),
            ]
            for col, value in enumerate(values):
                self.recommendations_table.setItem(row, col, QTableWidgetItem(value))
        self.update_data_gate()

    def _selected_recommendation(self) -> Optional[Dict[str, Any]]:
        row = self.recommendations_table.currentRow()
        if row < 0 and self.last_recommendations:
            row = 0
        if 0 <= row < len(self.last_recommendations):
            return self.last_recommendations[row]
        return None

    def save_selected_recommendation(self):
        item = self._selected_recommendation()
        if not item:
            return
        request = self.last_request or self.build_request()
        result = self.app_window.store.add_pension720_ticket(
            {
                'group': item.get('group'),
                'number': item.get('number'),
                'score': item.get('score'),
                'source': 'recommendation',
                'targetDrawNo': self.target_draw_spin.value(),
                'strategyRequest': request,
                'memo': str(get_pension720_strategy_meta(request.get('strategyId'))['label']),
            }
        )
        self._settle_saved_pension_tickets()
        self.refresh_view_state()
        self.app_window.show_status('연금복권 번호를 저장했습니다.' if result.get('inserted') else '이미 저장된 연금복권 번호입니다.', 4000)

    def save_selected_expansion(self):
        item = self._selected_recommendation()
        if not item:
            return
        request = self.last_request or self.build_request()
        now = dt.datetime.now().isoformat()
        groups = [int(item.get('group') or 1), *[int(group) for group in item.get('expansionGroups', [])]]
        rows = [
            {
                'group': group,
                'number': item.get('number'),
                'score': item.get('score'),
                'source': 'recommendation',
                'targetDrawNo': self.target_draw_spin.value(),
                'strategyRequest': request,
                'memo': str(get_pension720_strategy_meta(request.get('strategyId'))['label']),
                'createdAt': now,
            }
            for group in groups
        ]
        result = self.app_window.store.add_pension720_tickets_bulk(rows)
        self._settle_saved_pension_tickets()
        self.refresh_view_state()
        self.app_window.show_status(f"같은 번호 묶음 {result.get('inserted', 0)}개를 저장했어요.", 4000)

    def run_campaign_recommendation(self):
        if not self.pension720_stats:
            QMessageBox.warning(self, '묶음 구매', '연금복권 정보가 없습니다. [최신 정보 확인]을 먼저 눌러주세요.')
            return
        request = self.build_request()
        start_draw = self.campaign_start_spin.value()
        weeks = self.campaign_weeks_spin.value()
        sets_per_draw = self.campaign_sets_spin.value()
        size_error = campaign_size_error(weeks, sets_per_draw)
        if size_error:
            QMessageBox.warning(self, '묶음 구매', size_error)
            return

        def task() -> Dict[str, Any]:
            engine = Pension720Engine(self.pension720_stats)
            campaign_id = self.app_window.store.create_id('p720_campaign')
            tickets = []
            for index in range(weeks):
                seed = request.get('params', {}).get('seed')
                runtime_request = {
                    **request,
                    'params': {**(request.get('params') or {}), 'seed': None if seed is None else int(seed) + index},
                }
                recommendations = engine.recommend({'setCount': sets_per_draw, 'request': runtime_request})
                for item in recommendations:
                    tickets.append(
                        {
                            'group': item['group'],
                            'number': item['number'],
                            'score': item['score'],
                            'source': 'campaign',
                            'targetDrawNo': start_draw + index,
                            'campaignId': campaign_id,
                            'strategyRequest': runtime_request,
                            'memo': f"{get_pension720_strategy_meta(request.get('strategyId'))['label']} · {start_draw}-{start_draw + weeks - 1}회",
                            'createdAt': dt.datetime.now().isoformat(),
                        }
                    )
            return {'campaignId': campaign_id, 'tickets': tickets, 'request': request, 'startDrawNo': start_draw, 'weeks': weeks, 'setsPerDraw': sets_per_draw}

        self.campaign_btn.setEnabled(False)
        thread = TaskThread(task, self)
        self._task = thread
        thread.resultReady.connect(self._on_campaign_ready)
        thread.errorOccurred.connect(lambda message: QMessageBox.warning(self, '묶음 만들기 실패', message))
        thread.finished.connect(lambda: self.update_data_gate())
        thread.start()

    def _on_campaign_ready(self, payload: Dict[str, Any]):
        tickets = payload.get('tickets') or []
        if not tickets:
            QMessageBox.information(self, '묶음 구매', '만들어진 번호가 없습니다.')
            return
        campaign = {
            'id': payload['campaignId'],
            'name': f"{payload['startDrawNo']}회 시작 {payload['weeks']}회",
            'startDrawNo': payload['startDrawNo'],
            'weeks': payload['weeks'],
            'setsPerDraw': payload['setsPerDraw'],
            'strategyRequest': payload['request'],
        }
        size_error = campaign_size_error(payload['weeks'], payload['setsPerDraw'])
        if size_error or self.app_window.store.normalize_pension720_campaign(campaign) is None:
            QMessageBox.warning(self, '묶음 구매', size_error or '묶음 정보를 저장할 수 없어 번호를 저장하지 않았습니다.')
            return
        result = self.app_window.store.add_pension720_tickets_bulk(tickets)
        if result.get('inserted', 0) > 0:
            self.app_window.store.add_pension720_campaign(campaign)
        self._settle_saved_pension_tickets()
        self.refresh_view_state()
        self.app_window.show_status(f"묶음 번호 {result.get('inserted', 0)}개를 저장했어요.", 4000)

    @staticmethod
    def _pension_ticket_status(ticket: Dict[str, Any]) -> str:
        checked = ticket.get('checked') or {}
        if checked:
            label = str(checked.get('label') or '').strip()
            return f"{label}({checked.get('drawNo')}회)" if label else '확인'
        return '대기'

    @staticmethod
    def _source_label(source: Any) -> str:
        return {'recommendation': '추천받음', 'campaign': '묶음 구매'}.get(str(source or ''), str(source or '-'))

    def render_saved_tables(self):
        tickets = self.app_window.store.state['pension720Tickets']
        campaigns = self.app_window.store.state['pension720Campaigns']
        self.saved_summary_label.setText(f'{len(tickets)}개 저장됨')
        self.saved_table.setRowCount(0)
        for ticket in tickets:
            row = self.saved_table.rowCount()
            self.saved_table.insertRow(row)
            values = [
                f"{ticket.get('group')}조",
                str(ticket.get('number') or ''),
                str(ticket.get('targetDrawNo') or ''),
                self._source_label(ticket.get('source')),
                str(ticket.get('memo') or ''),
                str(ticket.get('createdAt') or '')[:10],
                self._pension_ticket_status(ticket),
            ]
            for col, value in enumerate(values):
                self.saved_table.setItem(row, col, QTableWidgetItem(value))
        self.campaign_table.setRowCount(0)
        for campaign in campaigns:
            row = self.campaign_table.rowCount()
            self.campaign_table.insertRow(row)
            values = [
                str(campaign.get('name') or ''),
                str(campaign.get('startDrawNo') or ''),
                str(campaign.get('weeks') or ''),
                str(campaign.get('setsPerDraw') or ''),
                str(self.app_window.store.count_pension720_tickets_by_campaign_id(str(campaign.get('id') or ''))),
            ]
            for col, value in enumerate(values):
                self.campaign_table.setItem(row, col, QTableWidgetItem(value))
        self.update_data_gate()

    def copy_saved_tickets(self):
        tickets = self.app_window.store.state['pension720Tickets']
        text = '\n'.join(f"{ticket.get('group')}조 {ticket.get('number')}" for ticket in tickets)
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        self.app_window.show_status('연금복권 저장 번호를 복사했습니다.', 4000)

    def export_saved_tickets_csv(self):
        tickets = self.app_window.store.state['pension720Tickets']
        if not tickets:
            return
        ts = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath, _ = QFileDialog.getSaveFileName(self, '연금복권 파일 저장', f'lotto_pension_pro_pension720_tickets_{ts}.csv', 'CSV 파일 (*.csv)')
        if not filepath:
            return
        try:
            Path(filepath).write_text(build_pension720_ticket_csv(tickets), encoding='utf-8-sig')
        except Exception as exc:
            logger.exception('Pension720 CSV export failed')
            QMessageBox.warning(self, '파일 저장', str(exc))
            return
        self.app_window.show_status('연금복권 저장 목록을 파일로 저장했어요.', 4000)

    def clear_saved_tickets(self):
        if not self.app_window.store.state['pension720Tickets']:
            return
        result = QMessageBox.question(self, '저장한 번호 지우기', '저장한 연금복권 번호와 묶음을 모두 지울까요?')
        if result != QMessageBox.StandardButton.Yes:
            return
        removed = self.app_window.store.clear_pension720_tickets()
        self.refresh_view_state()
        self.app_window.show_status(f'연금복권 저장 번호 {removed}개를 정리했습니다.', 4000)

    def run_saved_ticket_check(self):
        self.check_table.setRowCount(0)
        rows = [
            resolve_pension720_ticket_check(ticket, self.pension720_stats)
            for ticket in self.app_window.store.state['pension720Tickets']
        ]
        rows.sort(key=self._check_sort_value)
        for item in rows:
            ticket = item.get('ticket') or {}
            result = item.get('result') or {}
            row = self.check_table.rowCount()
            self.check_table.insertRow(row)
            values = [
                f"{ticket.get('group')}조 {ticket.get('number')}",
                str(item.get('statusLabel') or ''),
                str(item.get('drawNo') or ''),
                str(result.get('label') or '-'),
                str(result.get('prizeLabel') or '-'),
            ]
            for col, value in enumerate(values):
                self.check_table.setItem(row, col, QTableWidgetItem(value))
        self.app_window.show_status('저장한 번호 확인이 끝났어요.', 4000)

    def _check_sort_value(self, item: Dict[str, Any]) -> float:
        status_order = {'target': 0, 'reference': 20, 'pending': 40, 'missing': 45}
        result = item.get('result') or {}
        rank = result.get('rank')
        rank_value = 2.5 if rank == 'bonus' else float(rank or 99)
        return float(status_order.get(str(item.get('status')), 50)) + rank_value


