from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional, Sequence

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QCloseEvent, QFont
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from klotto.config import APP_CONFIG
from klotto.core.draws import estimate_latest_draw, split_missing_draws
from klotto.core.pension720_engine import Pension720Engine
from klotto.core.stats import WinningStatsManager
from klotto.core.sync_service import LottoSyncWorker
from klotto.core.strategy_engine import StrategyEngine
from klotto.data.app_state import get_shared_store
from klotto.data.exporter import DataExporter
from klotto.data.favorites import FavoritesManager
from klotto.data.history import HistoryManager
from klotto.logging import logger
from klotto.net.http import normalize_proxy_url
from klotto.ui.main_window.pages.backtest import BacktestPage
from klotto.ui.theme import ThemeManager
from klotto.ui.main_window.pages.check import CheckPage
from klotto.ui.main_window.pages.data import DataPage
from klotto.ui.main_window.pages.number_generation import NumberGenerationPage
from klotto.ui.main_window.pages.pension720 import Pension720Page
from klotto.ui.main_window.pages.settings import SettingsPage
from klotto.ui.main_window.pages.stats import StatsPage

class LottoApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.store = get_shared_store()
        self.favorites_manager = FavoritesManager(self.store)
        self.history_manager = HistoryManager(self.store)
        self.stats_manager = WinningStatsManager()
        self._active_sync_worker: Optional[LottoSyncWorker] = None
        self._sync_start_latest_draw = 0
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
        self.nav_list.addItems(['생성', '당첨 통계', 'AI 추천', '전략 시뮬레이션', '연금복권', '당첨 확인', '데이터 관리', '설정/동기화'])
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
        self.pension720_page = Pension720Page(self)
        self.check_page = CheckPage(self)
        self.data_page = DataPage(self)
        self.settings_page = SettingsPage(self)
        self.settings_page.syncRequested.connect(lambda: self.start_sync('standard'))
        self.settings_page.fullRepairRequested.connect(lambda: self.start_sync('full_repair'))

        for page in [self.generator_page, self.stats_page, self.ai_page, self.backtest_page, self.pension720_page, self.check_page, self.data_page, self.settings_page]:
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
            self.store.state['dataHealth'] = {
                'availability': 'none',
                'source': 'none',
                'latestDrawNo': 0,
                'message': '당첨 데이터가 없습니다.',
            }
            self.store.save()
            return
        latest_draw = max(int(draw.get('draw_no', 0)) for draw in winning_data)
        existing = {int(draw.get('draw_no', 0)) for draw in winning_data}
        expected_latest = estimate_latest_draw()
        stale_threshold = int(APP_CONFIG['LATEST_DRAW_STALE_THRESHOLD'])
        health_reference_draw = max(latest_draw, expected_latest - stale_threshold)
        missing = split_missing_draws(
            existing,
            health_reference_draw,
            current_draw=expected_latest,
            recent_window=int(APP_CONFIG['SYNC_RECENT_WINDOW']),
            allowed_missing=APP_CONFIG['ALLOWED_MISSING_DRAWS'],
        )
        is_full = latest_draw >= (expected_latest - stale_threshold) and not missing['all']
        availability = 'full' if is_full else 'partial'
        message = (
            '전체 당첨 이력 확보'
            if is_full
            else f"최근 누락 {len(missing['recent'])}건 / 과거 누락 {len(missing['historical'])}건 / 예상 최신 {expected_latest}회"
        )
        self.store.state['dataHealth'] = {'availability': availability, 'source': 'sqlite_db', 'latestDrawNo': latest_draw, 'message': message}
        self.store.save()

    def refresh_all_views(self):
        self.refresh_data_health()
        self.stats_page.refresh_data()
        self.generator_page.refresh_view_state()
        self.ai_page.refresh_view_state()
        self.backtest_page.refresh_view_state()
        self.pension720_page.refresh_view_state()
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

    def start_sync(self, mode: str = 'standard'):
        if self._active_sync_worker and self._active_sync_worker.isRunning():
            return
        normalized_mode = 'full_repair' if mode == 'full_repair' else 'standard'
        self._sync_start_latest_draw = self.get_latest_draw_no()
        worker = LottoSyncWorker(
            APP_CONFIG['LOTTO_HISTORY_DB'],
            recent_window=int(APP_CONFIG['SYNC_RECENT_WINDOW']),
            proxy_url=str(self.store.state.get('proxyUrl') or ''),
            mode=normalized_mode,
            historical_batch_size=int(APP_CONFIG['HISTORICAL_SYNC_BATCH_SIZE']),
        )
        self._active_sync_worker = worker
        self.settings_page.set_sync_in_progress(True)
        self.settings_page.append_log('전체 무결성 검사/복구를 시작했습니다.' if normalized_mode == 'full_repair' else '표준 동기화를 시작했습니다.')
        worker.finished.connect(self._on_sync_finished)
        worker.error.connect(self._on_sync_error)
        worker.start()

    def _on_sync_finished(self, summary: Dict[str, Any]):
        self._active_sync_worker = None
        self.settings_page.set_sync_in_progress(False)
        fetched_records = summary.get('fetched_records', [])
        failed_draws = summary.get('failed_draws', [])
        cancelled = bool(summary.get('cancelled'))
        mode = 'full_repair' if summary.get('mode') == 'full_repair' else 'standard'
        inserted = updated = unchanged = invalid = 0
        inserted_draws: List[int] = []
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
                inserted_draws.append(int(record['draw_no']))
            elif status == 'updated':
                updated += 1
            elif status == 'unchanged':
                unchanged += 1
            else:
                invalid += 1

        settled = self.store.settle_tickets_if_possible(self.store.state['ticketBook'], self.stats_manager.winning_data)
        applied_count = inserted + updated + unchanged
        if cancelled:
            final_status = 'cancelled'
        elif failed_draws and applied_count > 0:
            final_status = 'warning'
        elif failed_draws and applied_count == 0:
            final_status = 'failure'
        elif invalid and applied_count == 0:
            final_status = 'failure'
        else:
            final_status = 'success'

        now = dt.datetime.now().isoformat()
        latest = self.get_latest_draw_no()
        sync_meta = dict(self.store.state['syncMeta'])
        sync_meta['mode'] = mode
        sync_meta['currentSource'] = '전체 무결성 검사/복구' if mode == 'full_repair' else '표준 동기화'
        failure_message = ', '.join(str(item) for item in failed_draws[:10])
        summary_message = (
            f"status={final_status}, inserted={inserted}, updated={updated}, unchanged={unchanged}, invalid={invalid}, "
            f"failed={len(failed_draws)}, settled={settled}, recentMissing={summary.get('recentMissingCount', 0)}, "
            f"historicalMissing={summary.get('historicalMissingCount', 0)}"
        )
        if final_status == 'success':
            sync_meta['lastSuccessAt'] = now
            sync_meta['lastSuccessDrawNo'] = latest
            sync_meta['lastWarningAt'] = ''
            sync_meta['lastWarningMessage'] = ''
            sync_meta['lastFailureAt'] = ''
            sync_meta['lastFailureMessage'] = ''
        elif final_status == 'warning':
            sync_meta['lastWarningAt'] = now
            sync_meta['lastWarningMessage'] = failure_message or summary_message
            sync_meta['lastFailureAt'] = ''
            sync_meta['lastFailureMessage'] = ''
        elif final_status == 'failure':
            sync_meta['lastFailureAt'] = now
            sync_meta['lastFailureMessage'] = failure_message or summary_message
            sync_meta['lastWarningAt'] = ''
            sync_meta['lastWarningMessage'] = ''
        else:
            sync_meta['lastWarningAt'] = now
            sync_meta['lastWarningMessage'] = '동기화가 취소되었습니다.'
            sync_meta['lastFailureAt'] = ''
            sync_meta['lastFailureMessage'] = ''
        self.store.state['syncMeta'] = sync_meta
        summary['settledTickets'] = settled
        summary['status'] = final_status
        self.store.save()
        self.refresh_all_views()
        self.settings_page.append_log(summary_message)

        alert_prefs = self.store.get_alert_prefs()
        if inserted_draws and max(inserted_draws) > self._sync_start_latest_draw and alert_prefs.get('enableInApp') and alert_prefs.get('notifyOnNewResult'):
            latest_inserted = max(inserted_draws)
            notice = f'새 최신 회차 {latest_inserted}회 결과를 반영했습니다.'
            self.settings_page.append_log(notice)
            self.show_status(notice, 5000)

        status_message = {
            'success': '당첨 데이터 동기화 완료',
            'warning': '당첨 데이터 동기화 완료 (부분 실패)',
            'failure': '당첨 데이터 동기화 실패',
            'cancelled': '당첨 데이터 동기화 취소',
        }[final_status]
        self.show_status(status_message, 4000)

    def _on_sync_error(self, message: str):
        mode = 'standard'
        if self._active_sync_worker is not None:
            mode = 'full_repair' if self._active_sync_worker.mode == 'full_repair' else 'standard'
        self._active_sync_worker = None
        self.settings_page.set_sync_in_progress(False)
        now = dt.datetime.now().isoformat()
        self.store.state['syncMeta'] = {
            **self.store.state['syncMeta'],
            'mode': mode,
            'currentSource': '전체 무결성 검사/복구' if mode == 'full_repair' else '표준 동기화',
            'lastFailureAt': now,
            'lastFailureMessage': message,
        }
        self.store.save()
        self.settings_page.append_log(f'동기화 실패: {message}')
        self.show_status('당첨 데이터 동기화 실패', 4000)
        QMessageBox.warning(self, '동기화 실패', message)

    def save_proxy_url(self, raw_value: str) -> bool:
        raw = str(raw_value or '').strip()
        normalized = normalize_proxy_url(raw)
        if raw and not normalized:
            self.settings_page.append_log('프록시 저장 실패: http/https URL만 허용됩니다.')
            self.show_status('프록시 URL이 올바르지 않습니다.', 4000)
            return False
        saved = self.store.set_proxy_url(normalized)
        self.settings_page.refresh_status()
        self.settings_page.append_log(f"프록시 설정 저장: {saved or '사용 안 함'}")
        self.show_status('프록시 설정을 저장했습니다.', 4000)
        return True

    def update_alert_preferences(self, *, enable_in_app: bool, notify_on_new_result: bool) -> None:
        current = self.store.get_alert_prefs()
        updated = self.store.update_alert_prefs(
            enableInApp=enable_in_app,
            notifyOnNewResult=notify_on_new_result,
            enableSystemNotification=current.get('enableSystemNotification', False),
        )
        self.settings_page.refresh_status()
        self.settings_page.append_log(
            f"알림 설정 저장: 인앱={updated.get('enableInApp')} / 새 결과 알림={updated.get('notifyOnNewResult')} / 시스템={updated.get('enableSystemNotification')}"
        )
        self.show_status('알림 설정을 저장했습니다.', 3000)

    def closeEvent(self, a0: QCloseEvent | None):
        if a0 is None:
            return
        try:
            encoded_geometry = self.saveGeometry().toBase64().data()
            self.store.state['windowGeometry'] = encoded_geometry.decode('ascii')
            self.store.save()
        finally:
            super().closeEvent(a0)
