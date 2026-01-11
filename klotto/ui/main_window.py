import sys
import random
import datetime
from pathlib import Path
from typing import List, Set, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSpinBox, QCheckBox, QFrame, QScrollArea, 
    QMessageBox, QSystemTrayIcon, QMenu, QGroupBox, QGridLayout,
    QApplication
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QIcon, QFont, QAction, QCloseEvent

from klotto.config import APP_CONFIG
from klotto.utils import logger, ThemeManager
from klotto.core.analysis import NumberAnalyzer
from klotto.core.generator import SmartNumberGenerator
from klotto.core.stats import WinningStatsManager
from klotto.data.favorites import FavoritesManager
from klotto.data.history import HistoryManager
from klotto.ui.widgets import LottoBall, ResultRow, WinningInfoWidget
from klotto.ui.dialogs import (
    StatisticsDialog, HistoryDialog, FavoritesDialog, 
    RealStatsDialog, WinningCheckDialog, ExportImportDialog, QRCodeDialog
)

# ============================================================
# 메인 애플리케이션 클래스
# ============================================================
class LottoApp(QWidget):
    def __init__(self):
        super().__init__()
        self.generated_sets: List[List[int]] = []
        
        # 매니저 초기화
        self.favorites_manager = FavoritesManager()
        self.history_manager = HistoryManager()
        self.stats_manager = WinningStatsManager()
        self.smart_generator = SmartNumberGenerator(self.stats_manager)
        
        self.total_generated = 0
        self.last_generated_time: Optional[datetime.datetime] = None
        
        # 테마 리스너 등록
        ThemeManager.add_listener(self._on_theme_changed)
        
        self.initUI()
        self._setup_shortcuts()
        logger.info("Application started")
        
    def initUI(self):
        t = ThemeManager.get_theme()
        
        self.setWindowTitle(f"{APP_CONFIG['APP_NAME']} v{APP_CONFIG['VERSION']}")
        self.setGeometry(100, 100, *APP_CONFIG['WINDOW_SIZE'])
        
        # 메인 레이아웃
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 1. 헤더 영역 (제목 + 테마 토글 + 메뉴)
        header_layout = QHBoxLayout()
        
        title_label = QLabel(APP_CONFIG['APP_NAME'])
        title_label.setFont(QFont('Segoe UI', 24, QFont.Weight.Bold))
        title_label.setStyleSheet(f"color: {t['accent']}; letter-spacing: -0.5px;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # 다크모드 토글 버튼
        self.theme_btn = QPushButton("Light" if ThemeManager.get_theme_name() == 'dark' else "Dark")
        self.theme_btn.setFixedSize(60, 32)
        self.theme_btn.setCheckable(True)
        self.theme_btn.setChecked(ThemeManager.get_theme_name() == 'dark')
        self.theme_btn.clicked.connect(self._toggle_theme)
        self.theme_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['bg_tertiary']};
                color: {t['text_primary']};
                border-radius: 16px;
                font-size: 12px;
            }}
            QPushButton:checked {{
                background-color: {t['text_primary']};
                color: {t['bg_primary']};
            }}
        """)
        header_layout.addWidget(self.theme_btn)
        
        main_layout.addLayout(header_layout)
        
        # 2. 당첨 정보 위젯
        self.winning_info_widget = WinningInfoWidget()
        main_layout.addWidget(self.winning_info_widget)
        
        # 3. 설정 영역 (그룹박스)
        settings_group = QGroupBox("생성 설정")
        settings_layout = QVBoxLayout(settings_group)
        settings_layout.setSpacing(12)
        
        # 첫 번째 줄: 생성 개수, 연속 번호 제한
        row1_layout = QHBoxLayout()
        
        # 생성 개수
        row1_layout.addWidget(QLabel("생성 개수:"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, APP_CONFIG['MAX_SETS'])
        self.count_spin.setValue(5)
        self.count_spin.setFixedWidth(60)
        row1_layout.addWidget(self.count_spin)
        
        row1_layout.addSpacing(20)
        
        # 연속 번호 제한
        self.consecutive_chk = QCheckBox("연속 번호 제한 (최대 2쌍)")
        self.consecutive_chk.setChecked(True)
        self.consecutive_chk.setToolTip("연속된 번호(예: 1, 2)가 너무 많이 나오지 않도록 제한합니다.")
        row1_layout.addWidget(self.consecutive_chk)
        
        row1_layout.addStretch()
        settings_layout.addLayout(row1_layout)
        
        # 두 번째 줄: 스마트 옵션
        row2_layout = QHBoxLayout()
        
        self.smart_mode_chk = QCheckBox("스마트 생성 (통계 기반)")
        self.smart_mode_chk.setChecked(True)
        self.smart_mode_chk.toggled.connect(self._toggle_smart_options)
        row2_layout.addWidget(self.smart_mode_chk)
        
        # 스마트 세부 옵션
        self.smart_options_widget = QWidget()
        smart_opts_layout = QHBoxLayout(self.smart_options_widget)
        smart_opts_layout.setContentsMargins(0, 0, 0, 0)
        
        self.prefer_hot_chk = QCheckBox("핫 넘버 선호")
        self.prefer_hot_chk.setChecked(True)
        self.prefer_hot_chk.setToolTip("최근 자주 나온 번호에 가중치를 둡니다.")
        smart_opts_layout.addWidget(self.prefer_hot_chk)
        
        self.balance_chk = QCheckBox("홀짝 균형")
        self.balance_chk.setChecked(True)
        self.balance_chk.setToolTip("홀수와 짝수의 비율이 적절하도록 조정합니다.")
        smart_opts_layout.addWidget(self.balance_chk)
        
        self.smart_options_widget.setEnabled(True)
        row2_layout.addWidget(self.smart_options_widget)
        
        row2_layout.addStretch()
        settings_layout.addLayout(row2_layout)
        
        # 고급 설정 (고정수/제외수) - 접이식으로 하면 좋겠지만 일단 버튼으로 다이얼로그 띄우지 않고 심플하게
        # 공간 절약을 위해 제외수는 일단 생략하거나 나중에 추가
        
        main_layout.addWidget(settings_group)
        
        # 4. 버튼 영역 (메인 액션)
        btn_layout = QHBoxLayout()
        
        self.generate_btn = QPushButton("번호 생성하기")
        self.generate_btn.setObjectName("generateBtn")
        self.generate_btn.setMinimumHeight(50)
        self.generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.generate_btn.clicked.connect(self.generate_numbers)
        btn_layout.addWidget(self.generate_btn)
        
        main_layout.addLayout(btn_layout)
        
        # 5. 결과 영역 (스크롤 가능)
        results_frame = QFrame()
        results_frame.setFrameShape(QFrame.Shape.StyledPanel)
        results_frame.setStyleSheet(f"background-color: {t['bg_secondary']}; border-radius: 12px; border: 1px solid {t['border']};")
        results_frame_layout = QVBoxLayout(results_frame)
        results_frame_layout.setContentsMargins(1, 1, 1, 1)
        
        # 결과 헤더
        res_header = QHBoxLayout()
        res_header.setContentsMargins(15, 10, 15, 5)
        res_header.addWidget(QLabel("생성 결과"))
        res_header.addStretch()
        
        # 결과 초기화 버튼
        self.clear_btn = QPushButton("초기화")
        self.clear_btn.setObjectName("clearBtn")
        self.clear_btn.setFixedSize(60, 26)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear_results)
        res_header.addWidget(self.clear_btn)
        
        results_frame_layout.addLayout(res_header)
        
        # 스크롤 영역
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")
        
        self.results_container = QWidget()
        self.results_container.setStyleSheet("background: transparent;")
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.results_layout.setSpacing(0)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        
        # 초기 안내 메시지
        self.placeholder_label = QLabel("번호 생성하기 버튼을 눌러주세요.\n행운의 번호가 기다리고 있습니다!")
        self.placeholder_label.setObjectName("placeholderLabel")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_layout.addWidget(self.placeholder_label)
        
        self.scroll_area.setWidget(self.results_container)
        results_frame_layout.addWidget(self.scroll_area)
        
        main_layout.addWidget(results_frame, 1) # Stretch factor 1
        
        # 6. 하단 메뉴바 (추가 기능)
        bottom_menu_layout = QHBoxLayout()
        
        functions = [
            ("📊 통계", self._show_statistics),
            ("📜 히스토리", self._show_history),
            ("⭐ 즐겨찾기", self._show_favorites),
            ("📈 당첨통계", self._show_real_stats),
            ("🎯 당첨확인", self._show_winning_check),
            ("💾 데이터관리", self._show_data_manager),
        ]
        
        for text, callback in functions:
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {t['bg_tertiary']};
                    color: {t['text_primary']};
                    border: 1px solid {t['border']};
                    border-radius: 8px;
                    padding: 8px 12px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: {t['accent_light']};
                    color: {t['accent']};
                    border-color: {t['accent']};
                }}
            """)
            btn.clicked.connect(callback)
            bottom_menu_layout.addWidget(btn)
        
        main_layout.addLayout(bottom_menu_layout)
        
        # 저작권 / 버전 정보
        footer_label = QLabel(f"Lotto Generator Pro v{APP_CONFIG['VERSION']} | Good Luck!")
        footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_label.setStyleSheet(f"color: {t['text_muted']}; font-size: 11px; margin-top: 5px;")
        main_layout.addWidget(footer_label)
        
        self.setLayout(main_layout)
        self._apply_theme()
        
        # 시스템 트레이
        self._setup_tray_icon()
    
    def _setup_shortcuts(self):
        """단축키 설정"""
        # Enter 키로 생성
        self.generate_btn.setShortcut("Return")
    
    def _setup_tray_icon(self):
        """시스템 트레이 아이콘 설정"""
        self.tray_icon = QSystemTrayIcon(self)
        # 아이콘 설정 필요 (임시로 표준 아이콘 사용)
        style = self.style()
        icon = style.standardIcon(style.StandardPixmap.SP_ArrowUp) # 임시
        self.tray_icon.setIcon(icon)
        
        menu = QMenu()
        restore_action = QAction("열기", self)
        restore_action.triggered.connect(self.showNormal)
        quit_action = QAction("종료", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        
        menu.addAction(restore_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
    
    def _toggle_smart_options(self, checked):
        self.smart_options_widget.setEnabled(checked)
    
    def _toggle_theme(self):
        ThemeManager.toggle_theme()
        self.theme_btn.setText("Light" if ThemeManager.get_theme_name() == 'dark' else "Dark")
        self.theme_btn.setChecked(ThemeManager.get_theme_name() == 'dark')
    
    def _on_theme_changed(self):
        self._apply_theme()
        # 자식 위젯들은 자동으로 스타일시트 상속받거나 재적용됨
        # 하지만 일부 커스텀 스타일은 다시 적용 필요
        self.update()
    
    def _apply_theme(self):
        self.setStyleSheet(ThemeManager.get_stylesheet())
    
    def generate_numbers(self):
        """번호 생성 실행"""
        try:
            count = self.count_spin.value()
            result_sets = []
            
            # 옵션 가져오기
            use_smart = self.smart_mode_chk.isChecked()
            prefer_hot = self.prefer_hot_chk.isChecked()
            balance_mode = self.balance_chk.isChecked()
            limit_consecutive = self.consecutive_chk.isChecked()
            
            # 고정수/제외수 (현재 UI에는 없지만 추후 확장성을 위해)
            fixed_nums = set() 
            exclude_nums = set()
            
            for _ in range(count):
                max_retries = 100
                nums = []
                
                for _ in range(max_retries):
                    if use_smart:
                        nums = self.smart_generator.generate_smart_numbers(
                            fixed_nums=fixed_nums,
                            exclude_nums=exclude_nums,
                            prefer_hot=prefer_hot,
                            balance_mode=balance_mode
                        )
                    else:
                        # 일반 랜덤
                        available = set(range(1, 46)) - fixed_nums - exclude_nums
                        remaining = 6 - len(fixed_nums)
                        nums = sorted(list(fixed_nums) + random.sample(list(available), remaining))
                    
                    # 제약 조건 체크
                    valid = True
                    
                    # 1. 연속 번호 체크
                    if limit_consecutive:
                        consecutive_cnt = sum(1 for i in range(len(nums)-1) if nums[i+1] == nums[i] + 1)
                        if consecutive_cnt > 2:  # 2쌍 초과 허용 안함
                            valid = False
                    
                    # 2. 중복 히스토리 체크 (최근 100개)
                    if self.history_manager.is_duplicate(nums):
                        valid = False
                        
                    if valid:
                        break
                
                result_sets.append(nums)
                # 히스토리 저장
                self.history_manager.add(nums)
            
            self._display_results(result_sets)
            self.generated_sets = result_sets
            self.total_generated += count
            self.last_generated_time = datetime.datetime.now()
            
            # 상태바 같은 곳에 메시지 표시하면 좋음
            
        except Exception as e:
            logger.error(f"Generate Error: {e}")
            QMessageBox.critical(self, "오류", f"번호 생성 중 오류가 발생했습니다.\n{str(e)}")
    
    def _display_results(self, sets: List[List[int]]):
        """결과 화면 표시"""
        # 플레이스홀더 제거
        self.placeholder_label.setVisible(False)
        
        # 기존 결과 위에 추가 (역순으로 추가하여 최신이 위로? 아니면 아래로? 보통 아래로 쌓임)
        # 여기서는 매번 Clear 하지 않고 추가하는 방식이 좋지만, 
        # 사용성을 위해 "새로 생성" 시 초기화하거나, 옵션을 줄 수 있음.
        # 일단 현재 로직은 기존꺼 유지하고 아래에 추가하는 방식
        
        # 구분선 (이전 생성과 구분을 위해)
        if self.results_layout.count() > 1: # 플레이스홀더 제외
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setStyleSheet(f"background-color: {ThemeManager.get_theme()['border_light']}; margin: 10px 0;")
            self.results_layout.addWidget(line)
        
        # 최신 당첨 번호 (비교용)
        winning_nums, bonus = self.winning_info_widget.get_winning_numbers()
        
        for i, nums in enumerate(sets):
            # 분석
            analysis = NumberAnalyzer.analyze(nums)
            
            # 당첨 번호와 매칭
            matched_info = NumberAnalyzer.compare_with_winning(nums, winning_nums, bonus)
            matched_nums = matched_info.get('matched', [])
            
            # Row 위젯 생성
            idx = self.total_generated + i + 1
            row = ResultRow(idx, nums, analysis, matched_nums)
            
            # 시그널 연결
            row.favoriteClicked.connect(self._add_to_favorites)
            row.copyClicked.connect(self._on_copy)
            
            self.results_layout.addWidget(row)
            
        # 스크롤 최하단으로 이동
        QTimer.singleShot(100, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))
    
    def clear_results(self):
        """결과 초기화"""
        while self.results_layout.count():
            child = self.results_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        self.placeholder_label = QLabel("번호 생성하기 버튼을 눌러주세요.\n행운의 번호가 기다리고 있습니다!")
        self.placeholder_label.setObjectName("placeholderLabel")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_layout.addWidget(self.placeholder_label)
        
        self.total_generated = 0
    
    def _add_to_favorites(self, numbers: List[int]):
        """즐겨찾기 추가"""
        if self.favorites_manager.add(numbers):
            # 토스트 메시지 대신 간단한 상태 표시나 로그
            # QMessageBox.information(self, "저장됨", "즐겨찾기에 저장되었습니다.")
            # UX를 위해 버튼 색상 변경 등을 하면 좋음
            pass
        else:
            QMessageBox.warning(self, "중복", "이미 즐겨찾기에 있는 번호입니다.")
            
    def _on_copy(self, numbers: List[int]):
        pass # ResultRow 내부에서 복사 처리함, 여기서는 추가 액션 필요시 구현
    
    # === 다이얼로그 표시 메서드들 ===
    
    def _show_statistics(self):
        dialog = StatisticsDialog(self.history_manager, self)
        dialog.exec()
        
    def _show_history(self):
        dialog = HistoryDialog(self.history_manager, self)
        dialog.exec()
        
    def _show_favorites(self):
        dialog = FavoritesDialog(self.favorites_manager, self)
        dialog.exec()
        
    def _show_real_stats(self):
        dialog = RealStatsDialog(self.stats_manager, self)
        dialog.exec()
        
    def _show_winning_check(self):
        dialog = WinningCheckDialog(self.favorites_manager, self.history_manager, self.stats_manager, self)
        dialog.exec()
        
    def _show_data_manager(self):
        dialog = ExportImportDialog(self.favorites_manager, self.history_manager, self.stats_manager, self)
        dialog.exec()
        
    def closeEvent(self, event: QCloseEvent):
        """종료 시 처리"""
        # 필요한 저장 작업 등이 있다면 여기서
        event.accept()
