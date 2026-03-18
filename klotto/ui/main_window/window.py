import datetime
from typing import List, Optional

from PyQt6.QtCore import Qt, QThread
from PyQt6.QtGui import QAction, QCloseEvent, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from klotto.config import APP_CONFIG
from klotto.core.generation_service import GenerationService
from klotto.core.generator import SmartNumberGenerator
from klotto.core.stats import WinningStatsManager
from klotto.data.favorites import FavoritesManager
from klotto.data.history import HistoryManager
from klotto.logging import logger
from klotto.ui.dialogs import (
    ExportImportDialog,
    FavoritesDialog,
    HistoryDialog,
    RealStatsDialog,
    StatisticsDialog,
    WinningCheckDialog,
)
from klotto.ui.main_window.controls_panel import GenerationControlsPanel
from klotto.ui.main_window.results_panel import ResultsPanel
from klotto.ui.theme import ThemeManager
from klotto.ui.widgets import WinningInfoWidget


class LottoApp(QWidget):
    MAX_GENERATE_RETRIES = 100

    def __init__(self):
        super().__init__()
        self.generated_sets: List[List[int]] = []
        self._sync_worker: Optional[QThread] = None

        self.favorites_manager = FavoritesManager()
        self.history_manager = HistoryManager()
        self.stats_manager = WinningStatsManager()
        self.smart_generator = SmartNumberGenerator(self.stats_manager)
        self.generation_service = GenerationService(self.history_manager, self.smart_generator)

        self.total_generated = 0
        self.last_generated_time: Optional[datetime.datetime] = None

        ThemeManager.add_listener(self._on_theme_changed)

        self.initUI()
        self._setup_shortcuts()
        logger.info("Application started")

    def initUI(self):
        theme = ThemeManager.get_theme()

        self.setWindowTitle(f"{APP_CONFIG['APP_NAME']} v{APP_CONFIG['VERSION']}")
        self.setGeometry(100, 100, *APP_CONFIG["WINDOW_SIZE"])

        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        header_layout = QHBoxLayout()
        self.title_label = QLabel(APP_CONFIG["APP_NAME"])
        self.title_label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        self.title_label.setStyleSheet(f"color: {theme['accent']}; letter-spacing: -0.5px;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        self.theme_btn = QPushButton("Light" if ThemeManager.get_theme_name() == "dark" else "Dark")
        self.theme_btn.setFixedSize(60, 32)
        self.theme_btn.setCheckable(True)
        self.theme_btn.setChecked(ThemeManager.get_theme_name() == "dark")
        self.theme_btn.clicked.connect(self._toggle_theme)
        header_layout.addWidget(self.theme_btn)
        main_layout.addLayout(header_layout)

        self.winning_info_widget = WinningInfoWidget()
        main_layout.addWidget(self.winning_info_widget)

        self.controls_panel = GenerationControlsPanel()
        main_layout.addWidget(self.controls_panel)

        btn_layout = QHBoxLayout()
        self.generate_btn = QPushButton("번호 생성하기")
        self.generate_btn.setObjectName("generateBtn")
        self.generate_btn.setMinimumHeight(50)
        self.generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.generate_btn.clicked.connect(self.generate_numbers)
        btn_layout.addWidget(self.generate_btn)
        main_layout.addLayout(btn_layout)

        self.results_panel = ResultsPanel()
        self.results_panel.cleared.connect(self._on_results_cleared)
        main_layout.addWidget(self.results_panel, 1)

        bottom_menu_layout = QHBoxLayout()
        functions = [
            ("📊 통계", self._show_statistics),
            ("📜 히스토리", self._show_history),
            ("⭐ 즐겨찾기", self._show_favorites),
            ("📈 당첨통계", self._show_real_stats),
            ("🎯 당첨확인", self._show_winning_check),
            ("📷 QR 스캔", self._show_qr_scanner),
            ("💾 데이터관리", self._show_data_manager),
        ]
        self.menu_buttons: List[QPushButton] = []
        for text, callback in functions:
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(callback)
            self.menu_buttons.append(btn)
            bottom_menu_layout.addWidget(btn)
        main_layout.addLayout(bottom_menu_layout)

        self.footer_label = QLabel(f"Lotto Generator Pro v{APP_CONFIG['VERSION']} | Good Luck!")
        self.footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.footer_label.setStyleSheet(f"color: {theme['text_muted']}; font-size: 11px; margin-top: 5px;")
        main_layout.addWidget(self.footer_label)

        self.setLayout(main_layout)
        self._apply_theme()
        self._setup_tray_icon()

    def _setup_shortcuts(self):
        self.generate_btn.setShortcut("Return")

    def _setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        style = self.style()
        if style is None:
            return
        icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowUp)
        self.tray_icon.setIcon(icon)

        menu = QMenu()
        restore_action = QAction("열기", self)
        restore_action.triggered.connect(self.showNormal)
        quit_action = QAction("종료", self)
        app = QApplication.instance()
        if app is not None:
            quit_action.triggered.connect(app.quit)

        menu.addAction(restore_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def _toggle_theme(self):
        ThemeManager.toggle_theme()

    def _on_theme_changed(self):
        self.theme_btn.setText("Light" if ThemeManager.get_theme_name() == "dark" else "Dark")
        self.theme_btn.setChecked(ThemeManager.get_theme_name() == "dark")
        self._apply_theme()

    def _apply_theme(self):
        theme = ThemeManager.get_theme()
        self.setStyleSheet(ThemeManager.get_stylesheet())
        self.title_label.setStyleSheet(f"color: {theme['accent']}; letter-spacing: -0.5px;")
        self.footer_label.setStyleSheet(f"color: {theme['text_muted']}; font-size: 11px; margin-top: 5px;")
        self.theme_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {theme['bg_tertiary']};
                color: {theme['text_primary']};
                border-radius: 16px;
                font-size: 12px;
            }}
            QPushButton:checked {{
                background-color: {theme['text_primary']};
                color: {theme['bg_primary']};
            }}
        """
        )
        menu_style = f"""
            QPushButton {{
                background-color: {theme['bg_tertiary']};
                color: {theme['text_primary']};
                border: 1px solid {theme['border']};
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {theme['accent_light']};
                color: {theme['accent']};
                border-color: {theme['accent']};
            }}
        """
        for button in self.menu_buttons:
            button.setStyleSheet(menu_style)
        self.results_panel.apply_theme()

    def generate_numbers(self):
        try:
            request = self.controls_panel.build_request(max_generate_retries=self.MAX_GENERATE_RETRIES)
            result = self.generation_service.generate_batch(request)
            if not result.generated_sets:
                QMessageBox.warning(
                    self,
                    "생성 실패",
                    f"요청 {result.requested_count}개 중 생성된 조합이 없습니다.\n실패: {result.failed_count}개",
                )
                return

            winning_numbers, bonus = self.winning_info_widget.get_winning_numbers()
            self.results_panel.display_results(
                result.generated_sets,
                start_index=self.total_generated,
                winning_numbers=winning_numbers,
                bonus=bonus,
                favorite_callback=self._add_to_favorites,
                copy_callback=self._on_copy,
            )

            self.generated_sets = result.generated_sets
            self.total_generated += len(result.generated_sets)
            self.last_generated_time = datetime.datetime.now()

            if result.failed_count > 0:
                QMessageBox.warning(
                    self,
                    "부분 생성 완료",
                    f"요청 {result.requested_count}개 / 생성 {len(result.generated_sets)}개 / 실패 {result.failed_count}개",
                )
        except ValueError as exc:
            QMessageBox.warning(self, "입력 오류", str(exc))
        except Exception as exc:
            logger.error("Generate Error: %s", exc)
            QMessageBox.critical(self, "오류", f"번호 생성 중 오류가 발생했습니다.\n{exc}")

    def clear_results(self):
        self.results_panel.clear_results()
        self._on_results_cleared()

    def _on_results_cleared(self):
        self.total_generated = 0

    def _add_to_favorites(self, numbers: List[int]):
        if not self.favorites_manager.add(numbers):
            QMessageBox.warning(self, "중복", "이미 즐겨찾기에 있는 번호입니다.")

    def _on_copy(self, numbers: List[int]):
        return None

    def _show_statistics(self):
        StatisticsDialog(self.history_manager, self).exec()

    def _show_history(self):
        HistoryDialog(self.history_manager, self).exec()

    def _show_favorites(self):
        FavoritesDialog(self.favorites_manager, self).exec()

    def _show_real_stats(self):
        RealStatsDialog(self.stats_manager, self).exec()

    def _show_winning_check(self):
        WinningCheckDialog(
            self.favorites_manager,
            self.history_manager,
            self.stats_manager,
            self,
        ).exec()

    def _show_qr_scanner(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            from klotto.ui.scanner import QRCodeScannerDialog
        finally:
            QApplication.restoreOverrideCursor()

        dialog = QRCodeScannerDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        payload = dialog.scanned_data
        if not payload:
            QMessageBox.warning(self, "스캔 실패", "스캔된 데이터를 찾지 못했습니다.")
            return

        WinningCheckDialog(
            self.favorites_manager,
            self.history_manager,
            self.stats_manager,
            self,
            qr_payload=payload,
        ).exec()

    def _show_data_manager(self):
        ExportImportDialog(self.favorites_manager, self.history_manager, self.stats_manager, self).exec()

    def closeEvent(self, a0: Optional[QCloseEvent]):
        try:
            sync_worker = getattr(self, "_sync_worker", None)
            if sync_worker and sync_worker.isRunning():
                sync_worker.cancel()
                sync_worker.wait(2000)

            if hasattr(self, "winning_info_widget") and self.winning_info_widget:
                self.winning_info_widget.network_manager.cancel()

            if hasattr(self, "tray_icon") and self.tray_icon:
                self.tray_icon.hide()
        except Exception as exc:
            logger.warning("Close cleanup error: %s", exc)

        if a0 is not None:
            a0.accept()
