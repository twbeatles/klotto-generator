import datetime
from typing import List, Dict, Tuple, Optional
from PyQt6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QFrame, 
    QPushButton, QSpinBox, QToolTip
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QPixmap, QImage, QPainter, QColor

from klotto.utils import logger, ThemeManager
from klotto.config import LOTTO_COLORS
from klotto.net.client import LottoNetworkManager

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

# ============================================================
# 로또 공 위젯
# ============================================================
class LottoBall(QLabel):
    """개별 로또 번호를 원형 공 모양으로 표시하는 위젯 - 3D 스타일"""
    
    def __init__(self, number: int, size: int = 40, highlighted: bool = False):
        super().__init__(str(number))
        self.number = number
        self._size = size
        self._highlighted = highlighted
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 크기에 따른 폰트 조정 (더 읽기 쉽게)
        font_size = max(11, size // 3)
        self.setFont(QFont('Segoe UI', font_size, QFont.Weight.Bold))
        self.update_style()
    
    def get_color_info(self) -> Dict:
        """번호 대역별 색상 정보 반환"""
        if 1 <= self.number <= 10:
            return LOTTO_COLORS['1-10']
        elif 11 <= self.number <= 20:
            return LOTTO_COLORS['11-20']
        elif 21 <= self.number <= 30:
            return LOTTO_COLORS['21-30']
        elif 31 <= self.number <= 40:
            return LOTTO_COLORS['31-40']
        else:
            return LOTTO_COLORS['41-45']
    
    def update_style(self):
        """3D 효과가 적용된 스타일 업데이트"""
        colors = self.get_color_info()
        bg = colors['bg']
        text = colors['text']
        gradient = colors['gradient']
        
        # 하이라이트 효과 (당첨 번호 일치 시)
        if self._highlighted:
            border_style = f"3px solid #FFD700"
            glow_effect = f"""
                QLabel {{
                    background: qradialgradient(cx:0.3, cy:0.3, radius:0.8, fx:0.2, fy:0.2,
                        stop:0 {gradient}, stop:0.4 {bg}, stop:1 {bg});
                    color: {text};
                    border-radius: {self._size // 2}px;
                    border: {border_style};
                }}
            """
        else:
            # 3D 입체감 효과 - 라디얼 그라디언트로 빛 반사 효과
            glow_effect = f"""
                QLabel {{
                    background: qradialgradient(cx:0.35, cy:0.25, radius:0.9, fx:0.25, fy:0.15,
                        stop:0 {gradient}, stop:0.5 {bg}, stop:1 {self._darken_color(bg, 15)});
                    color: {text};
                    border-radius: {self._size // 2}px;
                    border: 1px solid {self._darken_color(bg, 20)};
                }}
            """
        
        self.setStyleSheet(glow_effect)
    
    def _darken_color(self, hex_color: str, percent: int) -> str:
        """색상을 어둡게 만드는 헬퍼 함수"""
        try:
            hex_color = hex_color.lstrip('#')
            r = max(0, int(hex_color[0:2], 16) - percent * 255 // 100)
            g = max(0, int(hex_color[2:4], 16) - percent * 255 // 100)
            b = max(0, int(hex_color[4:6], 16) - percent * 255 // 100)
            return f'#{r:02x}{g:02x}{b:02x}'
        except Exception:
            return hex_color
    
    def set_highlighted(self, highlighted: bool):
        """하이라이트 상태 설정"""
        self._highlighted = highlighted
        self.update_style()


# ============================================================
# 결과 행 위젯
# ============================================================
class ResultRow(QWidget):
    """하나의 로또 세트(6개 번호)를 표시하는 행 - 개선된 UX"""
    favoriteClicked = pyqtSignal(list)
    copyClicked = pyqtSignal(list)
    
    def __init__(self, index: int, numbers: List[int], analysis: Dict = None,
                 matched_numbers: List[int] = None):
        super().__init__()
        self.index = index
        self.numbers = numbers
        self.analysis = analysis or {}
        self.matched_numbers = matched_numbers or []
        
        self._setup_ui(index)
    
    def _setup_ui(self, index: int):
        layout = QHBoxLayout()
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        
        t = ThemeManager.get_theme()
        
        # 인덱스 라벨 (배지 스타일)
        idx_label = QLabel(f"{index}")
        idx_label.setFixedSize(28, 28)
        idx_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        idx_label.setStyleSheet(f"""
            QLabel {{
                background-color: {t['accent_light']};
                color: {t['accent']};
                font-weight: bold;
                font-size: 12px;
                border-radius: 14px;
            }}
        """)
        layout.addWidget(idx_label)
        
        # 번호 공들 (간격 조정)
        self.balls = []
        for num in self.numbers:
            highlighted = num in self.matched_numbers
            ball = LottoBall(num, size=36, highlighted=highlighted)
            self.balls.append(ball)
            layout.addWidget(ball)
        
        # 구분선
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setStyleSheet(f"background-color: {t['border']}; max-width: 1px;")
        separator.setFixedHeight(24)
        layout.addWidget(separator)
        
        # 분석 결과 (간결하게)
        if self.analysis:
            total = self.analysis.get('total', 0)
            odd = self.analysis.get('odd', 0)
            even = self.analysis.get('even', 0)
            
            # 합계 표시 (적정 범위 색상)
            sum_color = t['success'] if 100 <= total <= 175 else t['text_muted']
            
            analysis_widget = QWidget()
            analysis_layout = QHBoxLayout(analysis_widget)
            analysis_layout.setContentsMargins(0, 0, 0, 0)
            analysis_layout.setSpacing(8)
            
            sum_label = QLabel(f"합 {total}")
            sum_label.setStyleSheet(f"color: {sum_color}; font-size: 12px; font-weight: bold;")
            analysis_layout.addWidget(sum_label)
            
            ratio_label = QLabel(f"홀{odd}:짝{even}")
            ratio_label.setStyleSheet(f"color: {t['text_muted']}; font-size: 11px;")
            analysis_layout.addWidget(ratio_label)
            
            layout.addWidget(analysis_widget)
        
        layout.addStretch()
        
        # 매칭 결과 표시 (더 눈에 띄게)
        if self.matched_numbers:
            match_count = len(self.matched_numbers)
            match_label = QLabel(f"✓ {match_count}")
            match_label.setFixedSize(36, 24)
            match_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            match_label.setStyleSheet(f"""
                QLabel {{
                    background-color: {t['success_light']};
                    color: {t['success']};
                    font-weight: bold;
                    font-size: 12px;
                    border-radius: 12px;
                }}
            """)
            match_label.setToolTip(f"{match_count}개 번호 일치")
            layout.addWidget(match_label)
        
        # 복사 버튼
        copy_btn = QPushButton("📋")
        copy_btn.setFixedSize(28, 28)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                font-size: 14px;
                border-radius: 14px;
            }}
            QPushButton:hover {{
                background: {t['bg_tertiary']};
            }}
        """)
        copy_btn.setToolTip("이 번호 복사")
        copy_btn.clicked.connect(self._copy_numbers)
        layout.addWidget(copy_btn)
        
        # QR 버튼
        qr_btn = QPushButton("📱")
        qr_btn.setFixedSize(28, 28)
        qr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        qr_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                font-size: 14px;
                border-radius: 14px;
            }}
            QPushButton:hover {{
                background: {t['bg_tertiary']};
            }}
        """)
        qr_btn.setToolTip("QR 코드 보기")
        qr_btn.clicked.connect(self._show_qr)
        layout.addWidget(qr_btn)
        
        # 즐겨찾기 버튼
        fav_btn = QPushButton("☆")
        fav_btn.setFixedSize(28, 28)
        fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fav_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                font-size: 16px;
                color: {t['warning']};
                border-radius: 14px;
            }}
            QPushButton:hover {{
                background: {t['warning_light']};
            }}
        """)
        fav_btn.setToolTip("즐겨찾기에 추가")
        fav_btn.clicked.connect(lambda: self.favoriteClicked.emit(self.numbers))
        layout.addWidget(fav_btn)
        
        self.setLayout(layout)
        self._apply_theme()
    
    def _copy_numbers(self):
        """번호를 클립보드에 복사"""
        from PyQt6.QtWidgets import QApplication
        nums_str = " ".join(f"{n:02d}" for n in self.numbers)
        QApplication.clipboard().setText(nums_str)
        self.copyClicked.emit(self.numbers)
    
    def _show_qr(self):
        """QR 코드 다이얼로그 표시"""
        from .dialogs import QRCodeDialog
        dialog = QRCodeDialog(self.numbers, self)
        dialog.exec()
    
    def _apply_theme(self):
        """테마 적용 - 홀수/짝수 행 배경색 차별화"""
        t = ThemeManager.get_theme()
        is_odd_row = self.index % 2 == 1
        bg_color = t['bg_secondary'] if is_odd_row else t['result_row_alt']
        
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {bg_color};
                border-bottom: 1px solid {t['border_light']};
            }}
            QWidget:hover {{
                background-color: {t['bg_hover']};
            }}
        """)


# ============================================================
# 당첨 정보 위젯
# ============================================================
class WinningInfoWidget(QWidget):
    """지난 회차 당첨 정보를 표시하는 위젯"""
    dataLoaded = pyqtSignal(dict)  # 당첨 정보 로드 시 시그널
    
    def __init__(self):
        super().__init__()
        self.network_manager = LottoNetworkManager(self)
        self.network_manager.dataLoaded.connect(self._on_data_received)
        self.network_manager.errorOccurred.connect(self._on_error)
        
        self.current_draw_no = self._get_estimated_latest_draw()
        self.current_data: Optional[Dict] = None
        self._is_collapsed = False
        self.initUI()
        self.load_winning_info(self.current_draw_no)
    
    def _get_estimated_latest_draw(self) -> int:
        """현재 날짜 기준 최신 회차 추정"""
        base_date = datetime.date(2002, 12, 7)
        today = datetime.date.today()
        days_diff = (today - base_date).days
        estimated_draw = days_diff // 7 + 1
        now = datetime.datetime.now()
        if today.weekday() == 5 and now.hour < 21:
            estimated_draw -= 1
        return max(1, estimated_draw)
    
    def initUI(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # 헤더
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)
        
        # 접기/펼치기 버튼
        self.toggle_btn = QPushButton("▼")
        self.toggle_btn.setFixedSize(28, 28)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._toggle_collapse)
        header_layout.addWidget(self.toggle_btn)
        
        title_label = QLabel("지난 회차 당첨 정보")
        title_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {ThemeManager.get_theme()['text_primary']};")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # 회차 선택
        self.draw_spinbox = QSpinBox()
        self.draw_spinbox.setRange(1, self.current_draw_no)
        self.draw_spinbox.setValue(self.current_draw_no)
        self.draw_spinbox.setFixedWidth(110)
        self.draw_spinbox.setSuffix(" 회")
        self.draw_spinbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.draw_spinbox.setToolTip("조회할 회차를 선택하세요")
        self.draw_spinbox.setStyleSheet("font-size: 14px; padding: 2px 5px;")
        header_layout.addWidget(self.draw_spinbox)
        
        self.refresh_btn = QPushButton("조회")
        self.refresh_btn.setFixedWidth(60)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._on_refresh_clicked)
        header_layout.addWidget(self.refresh_btn)
        
        layout.addLayout(header_layout)
        
        # 컨텐츠 컨테이너
        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)
        
        # 당첨 정보 프레임
        self.info_container = QFrame()
        self.info_container.setObjectName("infoContainer")
        info_layout = QVBoxLayout(self.info_container)
        info_layout.setContentsMargins(15, 12, 15, 12)
        info_layout.setSpacing(8)
        
        self.status_label = QLabel("로딩 중...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_layout.addWidget(self.status_label)
        
        self.numbers_widget = QWidget()
        self.numbers_layout = QHBoxLayout(self.numbers_widget)
        self.numbers_layout.setContentsMargins(0, 0, 0, 0)
        self.numbers_layout.setSpacing(8)
        self.numbers_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.numbers_widget.setVisible(False)
        info_layout.addWidget(self.numbers_widget)
        
        self.prize_widget = QWidget()
        self.prize_layout = QHBoxLayout(self.prize_widget)
        self.prize_layout.setContentsMargins(0, 4, 0, 0)
        self.prize_layout.setSpacing(15)
        self.prize_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prize_widget.setVisible(False)
        info_layout.addWidget(self.prize_widget)
        
        content_layout.addWidget(self.info_container)
        layout.addWidget(self.content_widget)
        
        self.setLayout(layout)
        self._apply_theme()
    
    def _apply_theme(self):
        t = ThemeManager.get_theme()
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['accent']};
                color: white;
                border-radius: 5px;
                padding: 5px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['accent_hover']}; }}
            QPushButton:disabled {{ background-color: {t['bg_tertiary']}; color: {t['text_muted']}; }}
        """)
        self.toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {t['text_secondary']};
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {t['bg_tertiary']};
                border-radius: 4px;
            }}
        """)
        self.status_label.setStyleSheet(f"color: {t['text_muted']}; font-size: 14px;")
    
    def _toggle_collapse(self):
        self._is_collapsed = not self._is_collapsed
        self.content_widget.setVisible(not self._is_collapsed)
        self.toggle_btn.setText("▶" if self._is_collapsed else "▼")
    
    def _on_refresh_clicked(self):
        self.load_winning_info(self.draw_spinbox.value())
    
    def load_winning_info(self, draw_no: int):
        """API로 당첨 정보 로드"""
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("로딩 중...")
        self.status_label.setVisible(True)
        self.numbers_widget.setVisible(False)
        self.prize_widget.setVisible(False)
        
        self.network_manager.fetch_draw(draw_no)
    
    def _on_data_received(self, data: dict):
        """API 데이터 수신 시 UI 업데이트"""
        self.current_data = data
        self.refresh_btn.setEnabled(True)
        self.status_label.setVisible(False)
        
        # 기존 위젯 클리어
        self._clear_layout(self.numbers_layout)
        self._clear_layout(self.prize_layout)
        
        draw_date = data.get('drwNoDate', '')
        draw_no = data.get('drwNo', 0)
        
        numbers = [
            data.get('drwtNo1'), data.get('drwtNo2'), data.get('drwtNo3'),
            data.get('drwtNo4'), data.get('drwtNo5'), data.get('drwtNo6')
        ]
        bonus = data.get('bnusNo')
        
        t = ThemeManager.get_theme()
        
        # 회차/날짜
        date_label = QLabel(f"<b>{draw_no}회</b> ({draw_date})")
        date_label.setStyleSheet(f"font-size: 13px; color: {t['text_secondary']};")
        self.numbers_layout.addWidget(date_label)
        
        # 당첨 번호
        for num in numbers:
            ball = LottoBall(num, size=34)
            self.numbers_layout.addWidget(ball)
        
        plus_label = QLabel("+")
        plus_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {t['text_muted']};")
        self.numbers_layout.addWidget(plus_label)
        
        bonus_ball = LottoBall(bonus, size=34)
        self.numbers_layout.addWidget(bonus_ball)
        
        bonus_label = QLabel("보너스")
        bonus_label.setStyleSheet(f"font-size: 11px; color: {t['text_muted']};")
        self.numbers_layout.addWidget(bonus_label)
        
        self.numbers_widget.setVisible(True)
        
        # 당첨금 정보
        first_prize = data.get('firstWinamnt', 0)
        first_winners = data.get('firstPrzwnerCo', 0)
        total_sales = data.get('totSellamnt', 0)
        
        prize_info = QLabel(f"🏆 <b style='color:{t['danger']};'>1등</b> <b>{first_prize:,}원</b> ({first_winners}명)")
        prize_info.setStyleSheet("font-size: 14px;")
        self.prize_layout.addWidget(prize_info)
        
        sales_info = QLabel(f"📊 판매액: <b>{total_sales:,}원</b>")
        sales_info.setStyleSheet(f"font-size: 13px; color: {t['text_secondary']};")
        self.prize_layout.addWidget(sales_info)
        
        self.prize_widget.setVisible(True)
        self.dataLoaded.emit(data)
    
    def _on_error(self, error_msg: str):
        self.refresh_btn.setEnabled(True)
        self.status_label.setText(f"⚠️ {error_msg}")
        self.status_label.setStyleSheet(f"color: {ThemeManager.get_theme()['danger']}; font-size: 14px;")
        self.status_label.setVisible(True)
        self.numbers_widget.setVisible(False)
        self.prize_widget.setVisible(False)
    
    def _clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
    
    def get_winning_numbers(self) -> Tuple[List[int], int]:
        """현재 로드된 당첨 번호 반환"""
        if not self.current_data:
            return [], 0
        
        numbers = [
            self.current_data.get('drwtNo1'), self.current_data.get('drwtNo2'),
            self.current_data.get('drwtNo3'), self.current_data.get('drwtNo4'),
            self.current_data.get('drwtNo5'), self.current_data.get('drwtNo6')
        ]
        bonus = self.current_data.get('bnusNo', 0)
        return numbers, bonus
