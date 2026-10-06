from __future__ import annotations

import datetime as dt
import time
from typing import Any, Dict, List, Optional, Sequence

from PyQt6.QtCore import QByteArray, QEventLoop, Qt, QThread, QTimer
from PyQt6.QtGui import QCloseEvent, QFont
from PyQt6.QtWidgets import (
    QApplication,
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
from klotto.ui.main_window.task_thread import TaskThread
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
        self._sync_applying = False
        self._sync_apply_cancelled = False
        self._sync_apply_state: Optional[Dict[str, Any]] = None
        ThemeManager.set_theme_name(self.store.state.get('theme', 'light'))
        ThemeManager.add_listener(self.apply_theme)
        self._setup_ui()
        self.refresh_data_health()
        self.refresh_all_views()
        self._notify_state_recovery()

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
        subtitle = QLabel('당첨 확인부터 번호 추천까지')
        nav_layout.addWidget(subtitle)
        self.nav_list = QListWidget()
        self.nav_list.addItems(['번호 생성', '당첨 통계', 'AI 추천', '지난 결과로 시험', '연금복권', '당첨 확인', '내 번호 관리', '설정·최신 정보'])
        nav_layout.addWidget(self.nav_list, 1)
        self.theme_toggle_btn = QPushButton('밝기 바꾸기')
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
        self.settings_page.syncCancelRequested.connect(self.cancel_sync)

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
        theme_name = ThemeManager.get_theme_name()
        if self.store.state.get('theme') != theme_name:
            self.store.state['theme'] = theme_name
            self.store.save()

    def toggle_theme(self):
        ThemeManager.toggle_theme()

    def _notify_state_recovery(self) -> None:
        issue = getattr(self.store, 'state_load_issue', None)
        if issue:
            QMessageBox.warning(
                self,
                '데이터 복구',
                '저장된 상태 파일에 문제가 있어 원본을 보존하고 새로 시작했습니다.\n\n' + str(issue),
            )

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
            QMessageBox.information(
                self,
                '먼저 최신 정보를 가져오세요',
                'AI 추천과 지난 결과 시험은 당첨 정보를 모두 가져온 뒤에 이용할 수 있습니다.\n\n'
                '설정·최신 정보에서 [최신 정보 가져오기]를 눌러주세요.',
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
            '최신 정보까지 모두 준비됨'
            if is_full
            else f"빠진 회차가 있어요(최근 {len(missing['recent'])}개·이전 {len(missing['historical'])}개). 설정에서 최신 정보를 가져오세요."
        )
        self.store.state['dataHealth'] = {'availability': availability, 'source': 'sqlite_db', 'latestDrawNo': latest_draw, 'message': message}
        self.store.save()

    def report_save_state(self) -> None:
        issue = getattr(self.store, 'last_save_error', None)
        if issue:
            self.show_status(f'저장하지 못했어요. 다시 시도해 주세요. ({issue})', 6000)

    def refresh_all_views(self):
        self.report_save_state()
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
            return [{'label': '구매한 번호', 'drawNo': ticket.get('targetDrawNo'), 'matches': 0, 'rank': '-', 'note': '아직 결과 없음'}]
        matches = len(set(ticket.get('numbers', [])) & set(target_draw.get('numbers', [])))
        rank = StrategyEngine([]).rank_ticket(ticket.get('numbers', []), target_draw.get('numbers', []), int(target_draw.get('bonus', 0)))
        return [{
            'label': '구매한 번호',
            'drawNo': ticket.get('targetDrawNo'),
            'matches': matches,
            'rank': rank,
            'note': ', '.join(str(value) for value in target_draw.get('numbers', [])),
        }]

    def start_sync(self, mode: str = 'standard'):
        if self._sync_applying:
            return
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
        self.settings_page.append_log('빠진 회차를 처음부터 모두 확인하고 있어요.' if normalized_mode == 'full_repair' else '최신 정보를 가져오기 시작했어요.')
        worker.finished.connect(self._on_sync_finished)
        worker.error.connect(self._on_sync_error)
        worker.progress.connect(self.settings_page.set_sync_progress)
        worker.start()

    def cancel_sync(self) -> None:
        worker = self._active_sync_worker
        if worker is None:
            if self._sync_applying:
                self._sync_apply_cancelled = True
                self.settings_page.append_log('반영 중단을 요청했어요.')
            return
        try:
            worker.cancel()
        except Exception as exc:
            logger.warning('Failed to cancel sync worker: %s', exc)
        self.settings_page.append_log('가져오기 중단을 요청했어요.')

    _SYNC_APPLY_CHUNK_SIZE = 100

    def _apply_sync_records(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        inserted = updated = unchanged = invalid = 0
        inserted_draws: List[int] = []
        for record in records:
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
        return {
            'inserted': inserted,
            'updated': updated,
            'unchanged': unchanged,
            'invalid': invalid,
            'inserted_draws': inserted_draws,
        }

    def _begin_chunked_apply(self, summary: Dict[str, Any], records: List[Dict[str, Any]]) -> None:
        self._sync_apply_state = {
            'summary': summary,
            'records': records,
            'index': 0,
            'inserted': 0,
            'updated': 0,
            'unchanged': 0,
            'invalid': 0,
            'inserted_draws': [],
        }
        self._sync_applying = True
        self._sync_apply_cancelled = False
        self.settings_page.set_sync_in_progress(True)
        self.settings_page.append_log(f'가져온 {len(records)}개를 반영하는 중이에요.')
        self.settings_page.set_sync_progress(0, len(records))
        QTimer.singleShot(0, self._apply_sync_chunk)

    def _apply_sync_chunk(self) -> None:
        state = self._sync_apply_state
        if state is None:
            return
        summary = state['summary']
        records = state['records']
        if self._sync_apply_cancelled:
            remaining = [int(item.get('draw_no', 0)) for item in records[state['index']:] if int(item.get('draw_no', 0)) > 0]
            summary = {**summary, 'cancelled': True, 'failed_draws': [*summary.get('failed_draws', []), *remaining]}
            self._finish_chunked_apply(summary)
            return
        chunk = records[state['index']:state['index'] + self._SYNC_APPLY_CHUNK_SIZE]
        counts = self._apply_sync_records(chunk)
        state['index'] += len(chunk)
        for key in ('inserted', 'updated', 'unchanged', 'invalid'):
            state[key] += counts[key]
        state['inserted_draws'].extend(counts['inserted_draws'])
        self.settings_page.set_sync_progress(state['index'], len(records))
        if state['index'] < len(records):
            QTimer.singleShot(0, self._apply_sync_chunk)
            return
        self._finish_chunked_apply(summary)

    def _finish_chunked_apply(self, summary: Dict[str, Any]) -> None:
        state = self._sync_apply_state
        self._sync_apply_state = None
        self._sync_applying = False
        self._sync_apply_cancelled = False
        self.settings_page.set_sync_in_progress(False)
        counts = state or {}
        self._finalize_sync(
            summary,
            inserted=int(counts.get('inserted', 0)),
            updated=int(counts.get('updated', 0)),
            unchanged=int(counts.get('unchanged', 0)),
            invalid=int(counts.get('invalid', 0)),
            inserted_draws=[int(item) for item in counts.get('inserted_draws', [])],
        )

    def _on_sync_finished(self, summary: Dict[str, Any]):
        self._active_sync_worker = None
        self.settings_page.set_sync_in_progress(False)
        fetched_records = list(summary.get('fetched_records', []))
        if summary.get('dbApplied'):
            try:
                self.stats_manager.reload_from_db()
            except Exception as exc:
                logger.warning('Failed to reload winning data after sync: %s', exc)
        if fetched_records and not summary.get('dbApplied'):
            if len(fetched_records) <= self._SYNC_APPLY_CHUNK_SIZE:
                counts = self._apply_sync_records(fetched_records)
                self._finalize_sync(summary, **counts)
            else:
                self._begin_chunked_apply(summary, fetched_records)
            return
        applied = summary.get('appliedCounts') or {}
        self._finalize_sync(
            summary,
            inserted=int(applied.get('inserted', 0)),
            updated=int(applied.get('updated', 0)),
            unchanged=int(applied.get('unchanged', 0)),
            invalid=int(applied.get('invalid', 0)),
            inserted_draws=[int(item) for item in summary.get('insertedDraws', [])],
        )

    def _finalize_sync(
        self,
        summary: Dict[str, Any],
        *,
        inserted: int,
        updated: int,
        unchanged: int,
        invalid: int,
        inserted_draws: List[int],
    ):
        failed_draws = summary.get('failed_draws', [])
        cancelled = bool(summary.get('cancelled'))
        mode = 'full_repair' if summary.get('mode') == 'full_repair' else 'standard'
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
        sync_meta['currentSource'] = '빠진 회차 모두 채우기' if mode == 'full_repair' else '최신 정보 가져오기'
        failure_message = ', '.join(str(item) for item in failed_draws[:10])
        summary_message = (
            f"새로 가져옴 {inserted}개·업데이트 {updated}개·이미 최신 {unchanged}개·"
            f"실패 {len(failed_draws)}개·구매 목록 확인 {settled}개"
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
            'success': '최신 정보를 모두 가져왔어요',
            'warning': '최신 정보를 가져왔지만 일부는 실패했어요',
            'failure': '최신 정보를 가져오지 못했어요',
            'cancelled': '가져오기를 중단했어요',
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
            'currentSource': '빠진 회차 모두 채우기' if mode == 'full_repair' else '최신 정보 가져오기',
            'lastFailureAt': now,
            'lastFailureMessage': message,
        }
        self.store.save()
        self.settings_page.append_log(f'가져오기 실패: {message}')
        self.show_status('최신 정보를 가져오지 못했어요', 4000)
        QMessageBox.warning(self, '가져오기 실패', message)

    def save_proxy_url(self, raw_value: str) -> bool:
        raw = str(raw_value or '').strip()
        normalized = normalize_proxy_url(raw)
        if raw and not normalized:
            self.settings_page.append_log('연결 주소 저장 실패: http:// 또는 https://로 시작해야 해요.')
            self.show_status('연결 주소가 올바르지 않습니다.', 4000)
            return False
        saved = self.store.set_proxy_url(normalized)
        self.settings_page.refresh_status()
        self.settings_page.append_log(f"연결 주소 저장: {saved or '사용 안 함'}")
        self.show_status('연결 주소를 저장했습니다.', 4000)
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
            f"알림 설정 저장: 앱 알림={'켬' if updated.get('enableInApp') else '끔'} / 새 결과 알림={'켬' if updated.get('notifyOnNewResult') else '끔'}"
        )
        self.show_status('알림 설정을 저장했습니다.', 3000)

    @staticmethod
    def _wait_for_thread(thread: QThread, timeout_s: float) -> bool:
        """이벤트를 펌핑하며 스레드 종료를 기다린다. 시간 내 종료 시 True.

        wait() 반환값을 무시하고 종료를 진행하면 실행 중인 QThread가 파괴되어
        프로세스가 abort하므로, 만료 여부를 반드시 확인해야 한다.
        """
        deadline = time.monotonic() + max(0.0, timeout_s)
        while thread.isRunning():
            remaining_ms = int(max(0.0, deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                return False
            thread.wait(min(remaining_ms, 200))
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        return True

    def _cancel_background_work(self) -> None:
        worker = self._active_sync_worker
        if worker is not None:
            try:
                worker.finished.disconnect(self._on_sync_finished)
            except (TypeError, RuntimeError):
                pass
            try:
                worker.error.disconnect(self._on_sync_error)
            except (TypeError, RuntimeError):
                pass
            try:
                worker.cancel()
            except Exception as exc:
                logger.warning('Failed to cancel sync worker: %s', exc)
            self.show_status('진행 중인 가져오기를 마무리하는 중이에요…')
            if not self._wait_for_thread(worker, timeout_s=15.0):
                logger.error('Sync worker did not stop within timeout; closing anyway')
        for task in self.findChildren(TaskThread):
            try:
                if task.isRunning() and not self._wait_for_thread(task, timeout_s=5.0):
                    logger.error('Background task did not stop within timeout; closing anyway')
            except Exception as exc:
                logger.warning('Failed to join background task: %s', exc)

    def closeEvent(self, a0: QCloseEvent | None):
        if a0 is None:
            return
        try:
            ThemeManager.remove_listener(self.apply_theme)
            self._cancel_background_work()
            encoded_geometry = self.saveGeometry().toBase64().data()
            self.store.state['windowGeometry'] = encoded_geometry.decode('ascii')
            self.store.save()
        finally:
            super().closeEvent(a0)
