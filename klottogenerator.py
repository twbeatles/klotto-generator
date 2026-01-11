"""
Lotto 6/45 Generator Pro v2.0
로또 번호 생성기 - 동행복권 API 연동, 다크모드, 번호 분석 지원
"""

import sys
import random
import datetime
import json
import urllib.request
import urllib.error
import logging
import os
from typing import List, Set, Dict, Optional, Tuple
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QMessageBox, QStyle,
    QSpinBox, QScrollArea, QLineEdit, QGroupBox, QGridLayout,
    QFrame, QCheckBox, QSpacerItem, QSizePolicy, QComboBox,
    QStatusBar, QToolTip, QDialog, QListWidget, QListWidgetItem,
    QDialogButtonBox, QToolButton
)
from PyQt6.QtGui import (
    QFont, QColor, QShortcut, QKeySequence, QPainter,
    QLinearGradient, QBrush, QPen, QRadialGradient, QPixmap, QImage
)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve, QSize, QUrl

try:
    import qrcode
    from PIL import ImageQt
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

# ============================================================
# 로깅 설정
# ============================================================
def setup_logging():
    """로깅 시스템 초기화"""
    log_dir = Path.home() / ".lotto_generator"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "app.log"
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ============================================================
# 상수 정의
# ============================================================
APP_CONFIG = {
    'APP_NAME': 'Lotto 6/45 Generator Pro',
    'VERSION': '2.2',
    'WINDOW_SIZE': (680, 980),
    'FAVORITES_FILE': Path.home() / ".lotto_generator" / "favorites.json",
    'HISTORY_FILE': Path.home() / ".lotto_generator" / "history.json",
    'MAX_SETS': 20,
    'MAX_FIXED_NUMS': 5,
    'OPTIMAL_SUM_RANGE': (100, 175),
    'API_TIMEOUT': 10,
    'MAX_HISTORY': 500,  # 최대 히스토리 개수
    'WINNING_STATS_FILE': Path.home() / ".lotto_generator" / "winning_stats.json",
    'WINNING_STATS_CACHE_SIZE': 100,  # 캐시할 최근 회차 수
}

LOTTO_COLORS = {
    '1-10': {'bg': '#FBC400', 'text': 'black', 'gradient': '#FFD700'},
    '11-20': {'bg': '#2980B9', 'text': 'white', 'gradient': '#3498DB'},
    '21-30': {'bg': '#C0392B', 'text': 'white', 'gradient': '#E74C3C'},
    '31-40': {'bg': '#7F8C8D', 'text': 'white', 'gradient': '#95A5A6'},
    '41-45': {'bg': '#27AE60', 'text': 'white', 'gradient': '#2ECC71'},
}

DHLOTTERY_API_URL = "https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={}"

# ============================================================
# 테마 시스템
# ============================================================
THEMES = {
    'light': {
        'name': '라이트',
        'bg_primary': '#F5F7FA',
        'bg_secondary': '#FFFFFF',
        'bg_tertiary': '#E8ECF0',
        'bg_hover': '#F0F3F7',
        'text_primary': '#2c3e50',
        'text_secondary': '#555555',
        'text_muted': '#888888',
        'border': '#E1E4E8',
        'border_light': '#F0F0F0',
        'accent': '#4A90D9',
        'accent_hover': '#3A7BC8',
        'accent_light': '#E8F4FD',
        'success': '#27AE60',
        'success_light': '#E8F8F0',
        'warning': '#F39C12',
        'warning_light': '#FEF5E7',
        'danger': '#E74C3C',
        'neutral': '#7F8C9A',
        'shadow': 'rgba(0, 0, 0, 0.08)',
        'shadow_medium': 'rgba(0, 0, 0, 0.12)',
        'glow': 'rgba(74, 144, 217, 0.3)',
        'card_bg': '#FFFFFF',
        'result_row_alt': '#FAFBFC',
    },
    'dark': {
        'name': '다크',
        'bg_primary': '#14171C',
        'bg_secondary': '#1C2028',
        'bg_tertiary': '#252B35',
        'bg_hover': '#2A313D',
        'text_primary': '#E8EAED',
        'text_secondary': '#A8B0BC',
        'text_muted': '#6B7280',
        'border': '#32394A',
        'border_light': '#2A303C',
        'accent': '#60A5FA',
        'accent_hover': '#3B82F6',
        'accent_light': '#1E3A5F',
        'success': '#34D399',
        'success_light': '#1A3D2E',
        'warning': '#FBBF24',
        'warning_light': '#3D3520',
        'danger': '#F87171',
        'neutral': '#6B7280',
        'shadow': 'rgba(0, 0, 0, 0.3)',
        'shadow_medium': 'rgba(0, 0, 0, 0.4)',
        'glow': 'rgba(96, 165, 250, 0.4)',
        'card_bg': '#1C2028',
        'result_row_alt': '#1A1E25',
    }
}

class ThemeManager:
    """테마 관리자"""
    _current_theme = 'light'
    _listeners = []
    
    @classmethod
    def get_theme(cls) -> Dict:
        return THEMES[cls._current_theme]
    
    @classmethod
    def get_theme_name(cls) -> str:
        return cls._current_theme
    
    @classmethod
    def toggle_theme(cls):
        cls._current_theme = 'dark' if cls._current_theme == 'light' else 'light'
        logger.info(f"Theme changed to: {cls._current_theme}")
        for listener in cls._listeners:
            listener()
    
    @classmethod
    def add_listener(cls, callback):
        cls._listeners.append(callback)
    
    @classmethod
    def get_stylesheet(cls) -> str:
        t = cls.get_theme()
        is_dark = cls._current_theme == 'dark'
        
        return f"""
            /* ===== 기본 위젯 스타일 ===== */
            QWidget {{
                background-color: {t['bg_primary']};
                font-family: 'Malgun Gothic', 'Segoe UI', sans-serif;
                color: {t['text_primary']};
            }}
            
            /* ===== 그룹박스 ===== */
            QGroupBox {{
                background-color: {t['bg_secondary']};
                border: 1px solid {t['border']};
                border-radius: 12px;
                margin-top: 12px;
                padding-top: 8px;
                font-size: 15px;
                font-weight: bold;
                color: {t['text_primary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 12px;
                left: 12px;
                background-color: {t['accent']};
                color: white;
                border-radius: 4px;
            }}

            /* ===== 입력 필드 ===== */
            QLineEdit, QSpinBox {{
                border: 1px solid {t['border']};
                border-radius: 8px;
                padding: 4px 12px;
                background-color: {t['bg_secondary']};
                color: {t['text_primary']};
                font-size: 14px;
                selection-background-color: {t['accent']};
            }}
            QLineEdit:focus, QSpinBox:focus {{
                border: 2px solid {t['accent']};
                background-color: {t['bg_primary']};
            }}
            QLineEdit:hover, QSpinBox:hover {{
                border-color: {t['accent']};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 20px;
                border: none;
                background-color: {t['bg_tertiary']};
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background-color: {t['accent']};
            }}
            
            /* ===== 체크박스 ===== */
            QCheckBox {{
                spacing: 10px;
                font-size: 14px;
                color: {t['text_secondary']};
                font-weight: 600;
            }}
            QCheckBox::indicator {{
                width: 20px;
                height: 20px;
                border: 2px solid {t['border']};
                border-radius: 5px;
                background-color: {t['bg_secondary']};
            }}
            QCheckBox::indicator:hover {{
                border-color: {t['accent']};
                background-color: {t['accent_light']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {t['accent']};
                border-color: {t['accent']};
                image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMiIgaGVpZ2h0PSIxMiIgdmlld0JveD0iMCAwIDEyIDEyIj48cGF0aCBmaWxsPSJ3aGl0ZSIgZD0iTTEwIDNMNC41IDguNSAyIDYiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgZmlsbD0ibm9uZSIvPjwvc3ZnPg==);
            }}
            
            /* ===== 스크롤 영역 ===== */
            QScrollArea {{
                background-color: {t['bg_secondary']};
                border: 1px solid {t['border']};
                border-radius: 12px;
            }}
            QScrollBar:vertical {{
                background-color: {t['bg_tertiary']};
                width: 10px;
                border-radius: 5px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {t['neutral']};
                border-radius: 4px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {t['accent']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            /* ===== 버튼 ===== */
            QPushButton {{
                border-radius: 8px;
                font-size: 15px;
                font-weight: bold;
                color: #FFFFFF;
                border: none;
                padding: 10px 18px;
            }}
            
            QPushButton#generateBtn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {t['accent']}, stop:1 {t['accent_hover']});
            }}
            QPushButton#generateBtn:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {t['accent_hover']}, stop:1 {t['accent']});
            }}
            QPushButton#generateBtn:pressed {{
                background-color: {t['accent_hover']};
                padding-top: 12px;
                padding-bottom: 8px;
            }}
            
            QPushButton#clearBtn {{
                background-color: {t['neutral']};
            }}
            QPushButton#clearBtn:hover {{
                background-color: {'#8B9AAB' if not is_dark else '#7C8A9A'};
            }}
            
            QPushButton#saveBtn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {t['success']}, stop:1 #1E8449);
            }}
            QPushButton#saveBtn:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1E8449, stop:1 {t['success']});
            }}
            
            QPushButton#copyBtn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {t['warning']}, stop:1 #D68910);
            }}
            QPushButton#copyBtn:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #D68910, stop:1 {t['warning']});
            }}
            
            QPushButton:disabled {{
                background-color: {t['bg_tertiary']};
                color: {t['text_muted']};
            }}
            
            /* ===== 상태바 ===== */
            QStatusBar {{
                background-color: {t['bg_secondary']};
                color: {t['text_secondary']};
                border-top: 1px solid {t['border']};
                padding: 4px 8px;
                font-size: 13px;
            }}
            
            /* ===== 툴팁 ===== */
            QToolTip {{
                background-color: {t['bg_tertiary']};
                color: {t['text_primary']};
                border: 1px solid {t['border']};
                padding: 6px 10px;
                border-radius: 6px;
                font-size: 13px;
            }}
            
            /* ===== 정보 컨테이너 ===== */
            QFrame#infoContainer {{
                background-color: {t['card_bg']};
                border: 1px solid {t['border']};
                border-radius: 12px;
            }}
            
            /* ===== 플레이스홀더 ===== */
            QLabel#placeholderLabel {{
                color: {t['text_muted']};
                font-size: 15px;
                padding: 50px;
                font-style: italic;
            }}
            
            /* ===== 다이얼로그 ===== */
            QDialog {{
                background-color: {t['bg_primary']};
            }}
            
            /* ===== 리스트 위젯 ===== */
            QListWidget {{
                background-color: {t['bg_secondary']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 10px 12px;
                border-radius: 6px;
                margin: 2px;
            }}
            QListWidget::item:hover {{
                background-color: {t['bg_hover']};
            }}
            QListWidget::item:selected {{
                background-color: {t['accent_light']};
                color: {t['accent']};
            }}
        """


# ============================================================
# 번호 분석기
# ============================================================
class NumberAnalyzer:
    """생성된 번호 분석"""
    
    @staticmethod
    def analyze(numbers: List[int]) -> Dict:
        """번호 세트 분석"""
        if not numbers or len(numbers) != 6:
            return {}
        
        total = sum(numbers)
        odd_count = sum(1 for n in numbers if n % 2 == 1)
        even_count = 6 - odd_count
        low_count = sum(1 for n in numbers if n <= 22)
        high_count = 6 - low_count
        
        # 번호대 분포
        ranges = {'1-10': 0, '11-20': 0, '21-30': 0, '31-40': 0, '41-45': 0}
        for n in numbers:
            if n <= 10: ranges['1-10'] += 1
            elif n <= 20: ranges['11-20'] += 1
            elif n <= 30: ranges['21-30'] += 1
            elif n <= 40: ranges['31-40'] += 1
            else: ranges['41-45'] += 1
        
        # 점수 계산 (적정 범위 기준)
        score = 100
        if total < 100 or total > 175:
            score -= 20
        if odd_count == 0 or even_count == 0:
            score -= 15
        if low_count == 0 or high_count == 0:
            score -= 15
        
        return {
            'total': total,
            'odd': odd_count,
            'even': even_count,
            'low': low_count,
            'high': high_count,
            'ranges': ranges,
            'score': max(0, score),
            'is_optimal': 100 <= total <= 175 and 2 <= odd_count <= 4
        }
    
    @staticmethod
    def compare_with_winning(numbers: List[int], winning: List[int], bonus: int) -> Dict:
        """당첨 번호와 비교"""
        if not numbers or not winning:
            return {}
        
        matched = set(numbers) & set(winning)
        bonus_matched = bonus in numbers
        
        # 등수 계산
        match_count = len(matched)
        rank = None
        if match_count == 6:
            rank = 1
        elif match_count == 5 and bonus_matched:
            rank = 2
        elif match_count == 5:
            rank = 3
        elif match_count == 4:
            rank = 4
        elif match_count == 3:
            rank = 5
        
        return {
            'matched': list(matched),
            'match_count': match_count,
            'bonus_matched': bonus_matched,
            'rank': rank
        }


# ============================================================
# API 워커
# ============================================================
# ============================================================
# API 매니저 (QNetworkAccessManager 기반)
# ============================================================
class LottoNetworkManager(QWidget):
    """동행복권 API 통신 관리자 (비동기)"""
    dataLoaded = pyqtSignal(dict)
    errorOccurred = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.manager.finished.connect(self._on_finished)
        self._current_reply: Optional[QNetworkReply] = None
        
    def fetch_draw(self, draw_no: int):
        """회차 정보 요청"""
        if self._current_reply and self._current_reply.isRunning():
            self._current_reply.abort()
            
        url = QUrl(DHLOTTERY_API_URL.format(draw_no))
        request = QNetworkRequest(url)
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, 
                         'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        logger.info(f"Requesting draw #{draw_no}")
        self._current_reply = self.manager.get(request)
        self._current_reply.setProperty('draw_no', draw_no)
        
    def cancel(self):
        """요청 취소"""
        if self._current_reply and self._current_reply.isRunning():
            self._current_reply.abort()
            self._current_reply = None
            
    def _on_finished(self, reply: QNetworkReply):
        """요청 완료 처리"""
        if reply != self._current_reply:
            return
            
        self._current_reply = None
        reply.deleteLater()
        
        draw_no = reply.property('draw_no')
        
        if reply.error() != QNetworkReply.NetworkError.NoError:
            if reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
                return # 취소됨
            
            error_msg = f"Network Error: {reply.errorString()}"
            logger.error(error_msg)
            self.errorOccurred.emit("네트워크 오류가 발생했습니다.")
            return
            
        try:
            data_bytes = reply.readAll()
            data_str = str(data_bytes, 'utf-8')
            data = json.loads(data_str)
            
            if data.get('returnValue') == 'success':
                logger.info(f"Successfully fetched draw #{draw_no}")
                self.dataLoaded.emit(data)
            else:
                self.errorOccurred.emit("해당 회차의 정보를 찾을 수 없습니다.")
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            self.errorOccurred.emit("데이터 파싱 오류")
        except Exception as e:
            logger.error(f"Unknown error: {e}")
            self.errorOccurred.emit(f"알 수 없는 오류: {str(e)}")


# ============================================================
# 역대 당첨 번호 통계 관리
# ============================================================
class WinningStatsManager:
    """역대 당첨 번호 통계 관리"""
    
    def __init__(self):
        self.stats_file = APP_CONFIG['WINNING_STATS_FILE']
        self.winning_data: List[Dict] = []
        self._load()
    
    def _load(self):
        """파일에서 통계 데이터 로드"""
        try:
            if self.stats_file.exists():
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    self.winning_data = json.load(f)
                logger.info(f"Loaded {len(self.winning_data)} winning records")
        except Exception as e:
            logger.error(f"Failed to load winning stats: {e}")
            self.winning_data = []
    
    def _save(self):
        """통계 데이터 저장 (Atomic)"""
        try:
            self.stats_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file = self.stats_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.winning_data, f, ensure_ascii=False, indent=2)
            # Atomic replacement
            if self.stats_file.exists():
                os.replace(temp_file, self.stats_file)
            else:
                os.rename(temp_file, self.stats_file)
        except Exception as e:
            logger.error(f"Failed to save winning stats: {e}")
            # Clean up temp file if exists
            try:
                if 'temp_file' in locals() and temp_file.exists():
                    temp_file.unlink()
            except: pass
    
    def add_winning_data(self, draw_no: int, numbers: List[int], bonus: int):
        """당첨 데이터 추가"""
        # 중복 체크
        if any(d['draw_no'] == draw_no for d in self.winning_data):
            return
        
        self.winning_data.append({
            'draw_no': draw_no,
            'numbers': sorted(numbers),
            'bonus': bonus,
            'date': datetime.datetime.now().isoformat()
        })
        
        # 회차순 정렬
        self.winning_data.sort(key=lambda x: x['draw_no'], reverse=True)
        
        # 캐시 크기 제한
        if len(self.winning_data) > APP_CONFIG['WINNING_STATS_CACHE_SIZE']:
            self.winning_data = self.winning_data[:APP_CONFIG['WINNING_STATS_CACHE_SIZE']]
        
        self._save()
    
    def get_frequency_analysis(self) -> Dict:
        """번호별 출현 빈도 분석"""
        if not self.winning_data:
            return {}
        
        # 번호별 출현 횟수
        number_counts = {i: 0 for i in range(1, 46)}
        bonus_counts = {i: 0 for i in range(1, 46)}
        
        for data in self.winning_data:
            for num in data['numbers']:
                number_counts[num] += 1
            bonus_counts[data['bonus']] += 1
        
        # 정렬
        sorted_by_count = sorted(number_counts.items(), key=lambda x: x[1], reverse=True)
        
        return {
            'total_draws': len(self.winning_data),
            'number_counts': number_counts,
            'bonus_counts': bonus_counts,
            'hot_numbers': sorted_by_count[:10],  # 핫 넘버 TOP 10
            'cold_numbers': sorted_by_count[-10:],  # 콜드 넘버 10개
        }
    
    def get_range_distribution(self) -> Dict:
        """번호대별 분포 분석"""
        if not self.winning_data:
            return {}
        
        ranges = {'1-10': 0, '11-20': 0, '21-30': 0, '31-40': 0, '41-45': 0}
        
        for data in self.winning_data:
            for n in data['numbers']:
                if n <= 10: ranges['1-10'] += 1
                elif n <= 20: ranges['11-20'] += 1
                elif n <= 30: ranges['21-30'] += 1
                elif n <= 40: ranges['31-40'] += 1
                else: ranges['41-45'] += 1
        
        return ranges
    
    def get_pair_analysis(self) -> Dict:
        """연속 당첨 쌍 분석 (같이 나온 번호 쌍)"""
        if not self.winning_data:
            return {}
        
        pair_counts = {}
        
        for data in self.winning_data:
            nums = data['numbers']
            for i in range(len(nums)):
                for j in range(i + 1, len(nums)):
                    pair = (nums[i], nums[j])
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1
        
        # 가장 많이 나온 쌍 TOP 10
        sorted_pairs = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)
        return {'top_pairs': sorted_pairs[:10]}
    
    def get_recent_trend(self, count: int = 10) -> List[Dict]:
        """최근 N회차 트렌드"""
        return self.winning_data[:count]


# ============================================================
# 통계 기반 스마트 번호 생성기
# ============================================================
class SmartNumberGenerator:
    """통계 기반 스마트 번호 생성"""
    
    def __init__(self, stats_manager: WinningStatsManager):
        self.stats_manager = stats_manager
    
    def generate_smart_numbers(self, fixed_nums: Set[int] = None, 
                                exclude_nums: Set[int] = None,
                                prefer_hot: bool = True,
                                balance_mode: bool = True) -> List[int]:
        """스마트 번호 생성"""
        fixed_nums = fixed_nums or set()
        exclude_nums = exclude_nums or set()
        
        # 통계 데이터 가져오기
        analysis = self.stats_manager.get_frequency_analysis()
        
        if not analysis:
            # 통계 데이터 없으면 일반 랜덤 생성
            available = set(range(1, 46)) - fixed_nums - exclude_nums
            remaining = 6 - len(fixed_nums)
            return sorted(list(fixed_nums) + random.sample(list(available), remaining))
        
        number_counts = analysis['number_counts']
        max_count = max(number_counts.values()) if number_counts.values() else 1
        
        # 초기 후보군 생성 (가중치 계산)
        candidates = []
        for num in range(1, 46):
            if num in fixed_nums or num in exclude_nums:
                continue
            
            count = number_counts.get(num, 0)
            if prefer_hot:
                weight = count + 1
            else:
                weight = max_count - count + 1
            candidates.append((num, weight))
        
        result = list(fixed_nums)
        
        # 번호 선택 루프
        while len(result) < 6 and candidates:
            # 균형 모드일 경우 유효한 후보 필터링
            current_candidates = candidates
            
            if balance_mode:
                valid_candidates = []
                remaining_slots = 6 - len(result)
                current_odd = sum(1 for n in result if n % 2 == 1)
                
                for num, weight in candidates:
                    is_odd = (num % 2 == 1)
                    
                    # 1. 홀수 과다 방지: 홀수가 이미 4개면 홀수 선택 불가
                    if is_odd and current_odd >= 4:
                        continue
                        
                    # 2. 짝수 과다 방지: (홀수 부족 방지)
                    # 짝수를 골랐을 때, 남은 자리를 모두 홀수로 채워도 최소 홀수(2개)를 만족 못하면 안됨
                    # 즉: 현재홀수 + (남은자리-1) < 2 이면 짝수 선택 불가
                    if not is_odd:
                        max_possible_odd = current_odd + (remaining_slots - 1)
                        if max_possible_odd < 2:
                            continue
                            
                    valid_candidates.append((num, weight))
                
                current_candidates = valid_candidates
                
            if not current_candidates:
                break
                
            # 가중치 기반 확률 선택
            total_weight = sum(w for n, w in current_candidates)
            if total_weight <= 0:
                # 비상시 (혹은 실수로) 랜덤 선택
                selected_tuple = random.choice(current_candidates)
            else:
                r = random.uniform(0, total_weight)
                cumulative = 0
                selected_tuple = None
                
                for item in current_candidates:
                    cumulative += item[1]
                    if cumulative >= r:
                        selected_tuple = item
                        break
                
                if not selected_tuple:
                    selected_tuple = current_candidates[-1]
            
            selected_num = selected_tuple[0]
            result.append(selected_num)
            
            # 선택된 번호 제거 (원본 후보군에서)
            candidates = [c for c in candidates if c[0] != selected_num]
        
        return sorted(result)
    
    def generate_balanced_set(self, count: int = 5, 
                               fixed_nums: Set[int] = None,
                               exclude_nums: Set[int] = None) -> List[List[int]]:
        """균형 잡힌 세트 생성 (다양한 전략 조합)"""
        results = []
        strategies = [
            {'prefer_hot': True, 'balance_mode': True},   # 핫넘버 + 균형
            {'prefer_hot': False, 'balance_mode': True},  # 콜드넘버 + 균형
            {'prefer_hot': True, 'balance_mode': False},  # 핫넘버만
        ]
        
        for i in range(count):
            strategy = strategies[i % len(strategies)]
            nums = self.generate_smart_numbers(
                fixed_nums=fixed_nums,
                exclude_nums=exclude_nums,
                **strategy
            )
            results.append(nums)
        
        return results


# ============================================================
# 데이터 내보내기/가져오기
# ============================================================
class DataExporter:
    """데이터 내보내기/가져오기"""
    
    @staticmethod
    def export_to_csv(data: List[Dict], filepath: str, data_type: str = 'favorites'):
        """CSV로 내보내기"""
        try:
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                if data_type == 'favorites':
                    f.write("번호1,번호2,번호3,번호4,번호5,번호6,메모,생성일\n")
                    for item in data:
                        nums = item.get('numbers', [])
                        memo = item.get('memo', '')
                        created = item.get('created_at', '')
                        f.write(f"{','.join(map(str, nums))},{memo},{created}\n")
                elif data_type == 'history':
                    f.write("번호1,번호2,번호3,번호4,번호5,번호6,생성일\n")
                    for item in data:
                        nums = item.get('numbers', [])
                        created = item.get('created_at', '')
                        f.write(f"{','.join(map(str, nums))},{created}\n")
                elif data_type == 'winning_stats':
                    f.write("회차,번호1,번호2,번호3,번호4,번호5,번호6,보너스\n")
                    for item in data:
                        draw_no = item.get('draw_no', '')
                        nums = item.get('numbers', [])
                        bonus = item.get('bonus', '')
                        f.write(f"{draw_no},{','.join(map(str, nums))},{bonus}\n")
            
            logger.info(f"Exported {len(data)} items to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to export CSV: {e}")
            return False
    
    @staticmethod
    def export_to_json(data: List[Dict], filepath: str):
        """JSON으로 내보내기"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Exported {len(data)} items to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to export JSON: {e}")
            return False
    
    @staticmethod
    def import_from_json(filepath: str) -> Optional[List[Dict]]:
        """JSON에서 가져오기"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"Imported {len(data)} items from {filepath}")
            return data
        except Exception as e:
            logger.error(f"Failed to import JSON: {e}")
            return None


# ============================================================
# 즐겨찾기 관리
# ============================================================
class FavoritesManager:
    """즐겨찾기 번호 관리"""
    
    def __init__(self):
        self.favorites_file = APP_CONFIG['FAVORITES_FILE']
        self.favorites: List[Dict] = []
        self._load()
    
    def _load(self):
        """파일에서 즐겨찾기 로드"""
        try:
            if self.favorites_file.exists():
                with open(self.favorites_file, 'r', encoding='utf-8') as f:
                    self.favorites = json.load(f)
                logger.info(f"Loaded {len(self.favorites)} favorites")
        except Exception as e:
            logger.error(f"Failed to load favorites: {e}")
            self.favorites = []
    
    def _save(self):
        """즐겨찾기를 파일에 저장 (Atomic)"""
        try:
            self.favorites_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file = self.favorites_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.favorites, f, ensure_ascii=False, indent=2)
            
            if self.favorites_file.exists():
                os.replace(temp_file, self.favorites_file)
            else:
                os.rename(temp_file, self.favorites_file)
            logger.info(f"Saved {len(self.favorites)} favorites")
        except Exception as e:
            logger.error(f"Failed to save favorites: {e}")
            try:
                if 'temp_file' in locals() and temp_file.exists():
                    temp_file.unlink()
            except: pass
    
    def add(self, numbers: List[int], memo: str = "") -> bool:
        """즐겨찾기 추가"""
        if any(f['numbers'] == numbers for f in self.favorites):
            return False
        
        self.favorites.append({
            'numbers': numbers,
            'memo': memo,
            'created_at': datetime.datetime.now().isoformat()
        })
        self._save()
        return True
    
    def remove(self, index: int):
        """즐겨찾기 삭제"""
        if 0 <= index < len(self.favorites):
            del self.favorites[index]
            self._save()
    
    def get_all(self) -> List[Dict]:
        return self.favorites.copy()


# ============================================================
# 히스토리 관리
# ============================================================
class HistoryManager:
    """생성된 번호 히스토리 관리"""
    
    def __init__(self):
        self.history_file = APP_CONFIG['HISTORY_FILE']
        self.history: List[Dict] = []
        self._load()
    
    def _load(self):
        """파일에서 히스토리 로드"""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
                logger.info(f"Loaded {len(self.history)} history entries")
        except Exception as e:
            logger.error(f"Failed to load history: {e}")
            self.history = []
    
    def _save(self):
        """히스토리를 파일에 저장 (Atomic)"""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file = self.history_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
                
            if self.history_file.exists():
                os.replace(temp_file, self.history_file)
            else:
                os.rename(temp_file, self.history_file)
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
            try:
                if 'temp_file' in locals() and temp_file.exists():
                    temp_file.unlink()
            except: pass
    
    def add(self, numbers: List[int]) -> bool:
        """히스토리에 추가 (중복 체크)"""
        sorted_nums = sorted(numbers)
        
        # 중복 체크
        for h in self.history:
            if h['numbers'] == sorted_nums:
                return False  # 이미 생성된 조합
        
        self.history.insert(0, {
            'numbers': sorted_nums,
            'created_at': datetime.datetime.now().isoformat()
        })
        
        # 최대 개수 제한
        if len(self.history) > APP_CONFIG['MAX_HISTORY']:
            self.history = self.history[:APP_CONFIG['MAX_HISTORY']]
        
        self._save()
        return True
    
    def is_duplicate(self, numbers: List[int]) -> bool:
        """중복 조합인지 확인"""
        sorted_nums = sorted(numbers)
        return any(h['numbers'] == sorted_nums for h in self.history)
    
    def get_all(self) -> List[Dict]:
        return self.history.copy()
    
    def get_recent(self, count: int = 50) -> List[Dict]:
        """최근 N개 히스토리"""
        return self.history[:count]
    
    def clear(self):
        """히스토리 전체 삭제"""
        self.history = []
        self._save()
    
    def get_statistics(self) -> Dict:
        """히스토리 기반 통계"""
        if not self.history:
            return {}
        
        # 번호별 출현 횟수
        number_counts = {i: 0 for i in range(1, 46)}
        for h in self.history:
            for num in h['numbers']:
                number_counts[num] += 1
        
        # 정렬
        sorted_by_count = sorted(number_counts.items(), key=lambda x: x[1], reverse=True)
        
        return {
            'total_sets': len(self.history),
            'number_counts': number_counts,
            'most_common': sorted_by_count[:10],
            'least_common': sorted_by_count[-10:]
        }


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
        hex_color = hex_color.lstrip('#')
        r = max(0, int(hex_color[0:2], 16) - percent * 255 // 100)
        g = max(0, int(hex_color[2:4], 16) - percent * 255 // 100)
        b = max(0, int(hex_color[4:6], 16) - percent * 255 // 100)
        return f'#{r:02x}{g:02x}{b:02x}'
    
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
        
        # 참고: 테마 리스너는 등록하지 않음 (메모리 누수 방지)
        # 부모 위젯에서 필요 시 _apply_theme() 직접 호출
        
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
        nums_str = " ".join(f"{n:02d}" for n in self.numbers)
        QApplication.clipboard().setText(nums_str)
        self.copyClicked.emit(self.numbers)
    
    def _show_qr(self):
        """QR 코드 다이얼로그 표시"""
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


# ============================================================
# QR 코드 다이얼로그
# ============================================================
class QRCodeDialog(QDialog):
    """생성된 번호를 QR 코드로 표시"""
    
    def __init__(self, numbers: List[int], parent=None):
        super().__init__(parent)
        self.numbers = sorted(numbers)
        self.setWindowTitle("📱 QR 코드")
        self.setFixedSize(300, 350)
        self._setup_ui()
        self._apply_theme()
        
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        t = ThemeManager.get_theme()
        
        # 안내 텍스트
        nums_str = " ".join(f"{n:02d}" for n in self.numbers)
        info_label = QLabel(f"번호: {nums_str}")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {t['text_primary']};")
        layout.addWidget(info_label)
        
        # QR 코드 이미지
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setFixedSize(200, 200)
        self.qr_label.setStyleSheet("background-color: white; border-radius: 10px;")
        
        if HAS_QRCODE:
            self._generate_qr()
        else:
            self.qr_label.setText("qrcode 라이브러리가\n설치되지 않았습니다.")
            
        layout.addWidget(self.qr_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['accent']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['accent_hover']}; }}
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
    
    def _generate_qr(self):
        try:
            # 텍스트 형식으로 생성 (단순 복사용)
            # 동행복권 URL 형식은 복잡하고 유효성 검증이 있어 단순 텍스트가 안전함
            data = f"Lotto 6/45 Generator\nNumbers: {self.numbers}"
            
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=2,
            )
            qr.add_data(data)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # PIL 이미지를 QPixmap으로 변환
            # ImageQt를 직접 사용하면 일부 환경에서 에러 발생 가능성 있어 안전하게 변환
            import io
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            qimg = QImage.fromData(buffer.getvalue())
            pixmap = QPixmap.fromImage(qimg)
            
            self.qr_label.setPixmap(pixmap.scaled(180, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            
        except Exception as e:
            logger.error(f"QR Code generation failed: {e}")
            self.qr_label.setText("QR 생성 실패")

    def _apply_theme(self):
        t = ThemeManager.get_theme()
        self.setStyleSheet(f"background-color: {t['bg_primary']};")


# ============================================================
# 통계 다이얼로그
# ============================================================
class StatisticsDialog(QDialog):
    """번호 통계 다이얼로그"""
    
    def __init__(self, history_manager, parent=None):
        super().__init__(parent)
        self.history_manager = history_manager
        self.setWindowTitle("📊 번호 통계")
        self.setMinimumSize(500, 450)
        self._setup_ui()
        self._apply_theme()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        t = ThemeManager.get_theme()
        stats = self.history_manager.get_statistics()
        
        # 헤더
        header_label = QLabel("생성 번호 통계")
        header_label.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {t['text_primary']};
        """)
        layout.addWidget(header_label)
        
        if not stats:
            no_data = QLabel("아직 생성된 번호가 없습니다.\n번호를 생성하면 통계가 표시됩니다.")
            no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_data.setStyleSheet(f"color: {t['text_muted']}; font-size: 14px; padding: 40px;")
            layout.addWidget(no_data)
        else:
            # 총 생성 수
            total_label = QLabel(f"총 {stats['total_sets']}개 조합 생성됨")
            total_label.setStyleSheet(f"color: {t['text_secondary']}; font-size: 14px;")
            layout.addWidget(total_label)
            
            # 가장 많이 나온 번호
            most_group = QGroupBox("🔥 가장 많이 선택된 번호")
            most_layout = QHBoxLayout(most_group)
            most_layout.setSpacing(5)
            for num, count in stats['most_common'][:7]:
                ball = LottoBall(num, size=32)
                most_layout.addWidget(ball)
                count_lbl = QLabel(f"({count})")
                count_lbl.setStyleSheet(f"color: {t['text_muted']}; font-size: 11px;")
                most_layout.addWidget(count_lbl)
            most_layout.addStretch()
            layout.addWidget(most_group)
            
            # 가장 적게 나온 번호
            least_group = QGroupBox("❄️ 가장 적게 선택된 번호")
            least_layout = QHBoxLayout(least_group)
            least_layout.setSpacing(5)
            for num, count in stats['least_common'][:7]:
                ball = LottoBall(num, size=32)
                least_layout.addWidget(ball)
                count_lbl = QLabel(f"({count})")
                count_lbl.setStyleSheet(f"color: {t['text_muted']}; font-size: 11px;")
                least_layout.addWidget(count_lbl)
            least_layout.addStretch()
            layout.addWidget(least_group)
            
            # 번호대별 분포
            range_group = QGroupBox("📈 번호대별 분포")
            range_layout = QGridLayout(range_group)
            
            range_counts = {r: 0 for r in ['1-10', '11-20', '21-30', '31-40', '41-45']}
            for h in self.history_manager.get_all():
                for num in h['numbers']:
                    if num <= 10: range_counts['1-10'] += 1
                    elif num <= 20: range_counts['11-20'] += 1
                    elif num <= 30: range_counts['21-30'] += 1
                    elif num <= 40: range_counts['31-40'] += 1
                    else: range_counts['41-45'] += 1
            
            total_nums = sum(range_counts.values()) or 1
            col = 0
            for range_name, count in range_counts.items():
                pct = count / total_nums * 100
                lbl = QLabel(f"{range_name}: {count} ({pct:.1f}%)")
                lbl.setStyleSheet(f"font-size: 13px; color: {t['text_secondary']};")
                range_layout.addWidget(lbl, 0, col)
                col += 1
            
            layout.addWidget(range_group)
        
        layout.addStretch()
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['neutral']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 24px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {t['bg_tertiary']};
                color: {t['text_primary']};
            }}
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.setLayout(layout)
    
    def _apply_theme(self):
        t = ThemeManager.get_theme()
        self.setStyleSheet(f"""
            QDialog {{ background-color: {t['bg_primary']}; }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {t['border']};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: {t['bg_secondary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                padding: 0 8px;
            }}
        """)


# ============================================================
# 히스토리 다이얼로그
# ============================================================
class HistoryDialog(QDialog):
    """생성 히스토리 다이얼로그"""
    
    def __init__(self, history_manager, parent=None):
        super().__init__(parent)
        self.history_manager = history_manager
        self.setWindowTitle("📜 생성 히스토리")
        self.setMinimumSize(550, 500)
        self._setup_ui()
        self._apply_theme()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        t = ThemeManager.get_theme()
        
        # 헤더
        header_layout = QHBoxLayout()
        header_label = QLabel("최근 생성된 번호 조합")
        header_label.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {t['text_primary']};
        """)
        header_layout.addWidget(header_label)
        
        header_layout.addStretch()
        
        # 히스토리 수
        count = len(self.history_manager.get_all())
        count_label = QLabel(f"총 {count}개")
        count_label.setStyleSheet(f"color: {t['text_muted']}; font-size: 13px;")
        header_layout.addWidget(count_label)
        
        layout.addLayout(header_layout)
        
        # 리스트 위젯
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self._refresh_list()
        layout.addWidget(self.list_widget, 1)
        
        # 버튼 영역
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        # 복사 버튼
        copy_btn = QPushButton("📋 복사")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['accent']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['accent_hover']}; }}
        """)
        copy_btn.clicked.connect(self._copy_selected)
        btn_layout.addWidget(copy_btn)
        
        # QR 버튼
        qr_btn = QPushButton("📱 QR")
        qr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        qr_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['success']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['success_light']}; color: {t['success']}; }}
        """)
        qr_btn.clicked.connect(self._show_selected_qr)
        btn_layout.addWidget(qr_btn)
        
        # 히스토리 삭제 버튼
        clear_btn = QPushButton("🗑️ 전체 삭제")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['danger']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #C0392B; }}
        """)
        clear_btn.clicked.connect(self._clear_history)
        btn_layout.addWidget(clear_btn)
        
        btn_layout.addStretch()
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['neutral']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {t['bg_tertiary']};
                color: {t['text_primary']};
            }}
        """)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def _apply_theme(self):
        t = ThemeManager.get_theme()
        self.setStyleSheet(f"""
            QDialog {{ background-color: {t['bg_primary']}; }}
            QListWidget {{
                background-color: {t['bg_secondary']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                padding: 5px;
            }}
            QListWidget::item {{
                padding: 10px 12px;
                border-radius: 6px;
                font-size: 14px;
            }}
            QListWidget::item:alternate {{ background-color: {t['result_row_alt']}; }}
            QListWidget::item:selected {{
                background-color: {t['accent_light']};
                color: {t['accent']};
            }}
            QListWidget::item:hover {{ background-color: {t['bg_hover']}; }}
        """)
    
    def _refresh_list(self):
        self.list_widget.clear()
        for h in self.history_manager.get_recent(100):
            numbers_str = " - ".join(f"{n:02d}" for n in h['numbers'])
            created = h.get('created_at', '')[:16].replace('T', ' ')
            
            item = QListWidgetItem(f"🎱  {numbers_str}   [{created}]")
            item.setData(Qt.ItemDataRole.UserRole, h['numbers'])
            self.list_widget.addItem(item)
    
    def _copy_selected(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            item = self.list_widget.item(row)
            numbers = item.data(Qt.ItemDataRole.UserRole)
            nums_str = " ".join(f"{n:02d}" for n in numbers)
            QApplication.clipboard().setText(nums_str)
            QMessageBox.information(self, "복사 완료", f"번호가 복사되었습니다:\n{nums_str}")
        else:
            QMessageBox.warning(self, "선택 필요", "복사할 항목을 선택하세요.")
            
    def _show_selected_qr(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            item = self.list_widget.item(row)
            numbers = item.data(Qt.ItemDataRole.UserRole)
            dialog = QRCodeDialog(numbers, self)
            dialog.exec()
        else:
            QMessageBox.warning(self, "선택 필요", "QR 코드를 볼 항목을 선택하세요.")
    
    def _clear_history(self):
        if not self.history_manager.get_all():
            QMessageBox.information(self, "알림", "삭제할 히스토리가 없습니다.")
            return
        
        reply = QMessageBox.question(
            self,
            "히스토리 삭제",
            "모든 히스토리를 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.history_manager.clear()
            self._refresh_list()
            QMessageBox.information(self, "완료", "히스토리가 삭제되었습니다.")


# ============================================================
# 즐겨찾기 다이얼로그
# ============================================================
class FavoritesDialog(QDialog):
    """즐겨찾기 목록 다이얼로그 - 개선된 UX"""
    
    def __init__(self, favorites_manager: FavoritesManager, parent=None):
        super().__init__(parent)
        self.favorites_manager = favorites_manager
        self.setWindowTitle("⭐ 즐겨찾기")
        self.setMinimumSize(500, 400)
        self._setup_ui()
        self._apply_theme()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        t = ThemeManager.get_theme()
        
        # 헤더
        header_label = QLabel("저장된 번호 조합")
        header_label.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {t['text_primary']};
            padding-bottom: 5px;
        """)
        layout.addWidget(header_label)
        
        # 즐겨찾기 수
        count = len(self.favorites_manager.get_all())
        count_label = QLabel(f"총 {count}개의 즐겨찾기")
        count_label.setStyleSheet(f"color: {t['text_muted']}; font-size: 13px;")
        layout.addWidget(count_label)
        self.count_label = count_label
        
        # 리스트 위젯
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self._refresh_list()
        layout.addWidget(self.list_widget, 1)
        
        # 버튼 영역
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        # 복사 버튼
        copy_btn = QPushButton("📋 복사")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['accent']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {t['accent_hover']};
            }}
        """)
        copy_btn.clicked.connect(self._copy_selected)
        btn_layout.addWidget(copy_btn)
        
        # 삭제 버튼
        delete_btn = QPushButton("🗑️ 삭제")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['danger']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #C0392B;
            }}
        """)
        delete_btn.clicked.connect(self._delete_selected)
        btn_layout.addWidget(delete_btn)
        
        btn_layout.addStretch()
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['neutral']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {t['bg_tertiary']};
                color: {t['text_primary']};
            }}
        """)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def _apply_theme(self):
        """테마 적용"""
        t = ThemeManager.get_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t['bg_primary']};
            }}
            QListWidget {{
                background-color: {t['bg_secondary']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                padding: 5px;
            }}
            QListWidget::item {{
                padding: 12px;
                border-radius: 6px;
                font-size: 14px;
                color: {t['text_primary']};
            }}
            QListWidget::item:alternate {{
                background-color: {t['result_row_alt']};
            }}
            QListWidget::item:selected {{
                background-color: {t['accent_light']};
                color: {t['accent']};
            }}
            QListWidget::item:hover {{
                background-color: {t['bg_hover']};
            }}
        """)
    
    def _refresh_list(self):
        """리스트 새로고침"""
        self.list_widget.clear()
        for fav in self.favorites_manager.get_all():
            numbers_str = " - ".join(f"{n:02d}" for n in fav['numbers'])
            created = fav.get('created_at', '')[:10]
            memo = fav.get('memo', '')
            
            display_text = f"🎱  {numbers_str}"
            if memo:
                display_text += f"  ({memo})"
            display_text += f"  [{created}]"
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, fav['numbers'])
            self.list_widget.addItem(item)
        
        # 카운트 업데이트
        if hasattr(self, 'count_label'):
            self.count_label.setText(f"총 {len(self.favorites_manager.get_all())}개의 즐겨찾기")
    
    def _copy_selected(self):
        """선택된 번호 복사"""
        row = self.list_widget.currentRow()
        if row >= 0:
            item = self.list_widget.item(row)
            numbers = item.data(Qt.ItemDataRole.UserRole)
            nums_str = " ".join(f"{n:02d}" for n in numbers)
            QApplication.clipboard().setText(nums_str)
            QMessageBox.information(self, "복사 완료", f"번호가 클립보드에 복사되었습니다:\n{nums_str}")
        else:
            QMessageBox.warning(self, "선택 필요", "복사할 항목을 선택하세요.")
    
    def _delete_selected(self):
        """선택 항목 삭제 (확인 다이얼로그)"""
        row = self.list_widget.currentRow()
        if row >= 0:
            reply = QMessageBox.question(
                self, 
                "삭제 확인", 
                "선택한 즐겨찾기를 삭제하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.favorites_manager.remove(row)
                self._refresh_list()
        else:
            QMessageBox.warning(self, "선택 필요", "삭제할 항목을 선택하세요.")


# ============================================================
# 실제 당첨 번호 통계 다이얼로그
# ============================================================
class RealStatsDialog(QDialog):
    """실제 당첨 번호 통계 다이얼로그"""
    
    def __init__(self, stats_manager: WinningStatsManager, parent=None):
        super().__init__(parent)
        self.stats_manager = stats_manager
        self.setWindowTitle("📈 실제 당첨 번호 통계")
        self.setMinimumSize(600, 550)
        self._setup_ui()
        self._apply_theme()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        t = ThemeManager.get_theme()
        
        # 통계 데이터 가져오기
        analysis = self.stats_manager.get_frequency_analysis()
        range_dist = self.stats_manager.get_range_distribution()
        pair_analysis = self.stats_manager.get_pair_analysis()
        recent = self.stats_manager.get_recent_trend(5)
        
        if not analysis:
            # 데이터 없음 안내
            no_data_label = QLabel("📊 아직 수집된 당첨 데이터가 없습니다.\n\n"
                                   "당첨 정보 위젯에서 회차를 조회하면\n"
                                   "자동으로 통계가 수집됩니다.")
            no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_data_label.setStyleSheet(f"color: {t['text_muted']}; font-size: 15px;")
            layout.addWidget(no_data_label)
            
            close_btn = QPushButton("닫기")
            close_btn.clicked.connect(self.close)
            layout.addWidget(close_btn)
            return
        
        # 통계 요약
        summary_label = QLabel(f"📊 총 {analysis['total_draws']}회차 분석 결과")
        summary_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {t['accent']};")
        layout.addWidget(summary_label)
        
        # 핫 넘버 그룹
        hot_group = QGroupBox("🔥 핫 넘버 TOP 10 (가장 많이 나온 번호)")
        hot_layout = QHBoxLayout(hot_group)
        hot_layout.setSpacing(8)
        
        for num, count in analysis['hot_numbers']:
            ball = LottoBall(num, size=36)
            hot_layout.addWidget(ball)
            count_label = QLabel(f"({count})")
            count_label.setStyleSheet(f"color: {t['text_muted']}; font-size: 11px;")
            hot_layout.addWidget(count_label)
        
        hot_layout.addStretch()
        layout.addWidget(hot_group)
        
        # 콜드 넘버 그룹
        cold_group = QGroupBox("❄️ 콜드 넘버 (가장 적게 나온 번호)")
        cold_layout = QHBoxLayout(cold_group)
        cold_layout.setSpacing(8)
        
        for num, count in analysis['cold_numbers']:
            ball = LottoBall(num, size=36)
            cold_layout.addWidget(ball)
            count_label = QLabel(f"({count})")
            count_label.setStyleSheet(f"color: {t['text_muted']}; font-size: 11px;")
            cold_layout.addWidget(count_label)
        
        cold_layout.addStretch()
        layout.addWidget(cold_group)
        
        # 번호대별 분포
        if range_dist:
            range_group = QGroupBox("📊 번호대별 분포")
            range_layout = QVBoxLayout(range_group)
            
            total_nums = sum(range_dist.values())
            
            for range_name, count in range_dist.items():
                pct = (count / total_nums * 100) if total_nums > 0 else 0
                row_layout = QHBoxLayout()
                
                range_label = QLabel(f"{range_name}:")
                range_label.setFixedWidth(60)
                range_label.setStyleSheet(f"font-weight: bold; color: {t['text_primary']};")
                
                # 프로그레스 바 효과 (텍스트)
                bar_width = int(pct * 2)
                bar = QLabel("█" * bar_width)
                bar.setStyleSheet(f"color: {t['accent']};")
                
                pct_label = QLabel(f"{count}회 ({pct:.1f}%)")
                pct_label.setStyleSheet(f"color: {t['text_secondary']};")
                
                row_layout.addWidget(range_label)
                row_layout.addWidget(bar)
                row_layout.addWidget(pct_label)
                row_layout.addStretch()
                
                range_layout.addLayout(row_layout)
            
            layout.addWidget(range_group)
        
        # 최근 당첨 번호
        if recent:
            recent_group = QGroupBox("📅 최근 당첨 번호")
            recent_layout = QVBoxLayout(recent_group)
            
            for data in recent[:5]:
                row = QHBoxLayout()
                draw_label = QLabel(f"#{data['draw_no']}회")
                draw_label.setFixedWidth(70)
                draw_label.setStyleSheet(f"font-weight: bold; color: {t['accent']};")
                row.addWidget(draw_label)
                
                for num in data['numbers']:
                    ball = LottoBall(num, size=30)
                    row.addWidget(ball)
                
                # 보너스
                plus_label = QLabel("+")
                plus_label.setStyleSheet(f"color: {t['text_muted']};")
                row.addWidget(plus_label)
                
                bonus_ball = LottoBall(data['bonus'], size=30, highlighted=True)
                row.addWidget(bonus_ball)
                
                row.addStretch()
                recent_layout.addLayout(row)
            
            layout.addWidget(recent_group)
        
        layout.addStretch()
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.setMinimumHeight(40)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
    
    def _apply_theme(self):
        t = ThemeManager.get_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t['bg_primary']};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {t['border']};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: {t['bg_secondary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                padding: 0 8px;
            }}
            QPushButton {{
                background-color: {t['accent']};
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                padding: 10px;
            }}
            QPushButton:hover {{
                background-color: {t['accent_hover']};
            }}
        """)


# ============================================================
# 당첨 확인 자동화 다이얼로그
# ============================================================
class WinningCheckDialog(QDialog):
    """당첨 확인 자동화 다이얼로그"""
    
    def __init__(self, favorites_manager: FavoritesManager, 
                 history_manager, stats_manager: WinningStatsManager, parent=None):
        super().__init__(parent)
        self.favorites_manager = favorites_manager
        self.history_manager = history_manager
        self.stats_manager = stats_manager
        self.setWindowTitle("🎯 당첨 확인")
        self.setMinimumSize(650, 500)
        self._setup_ui()
        self._apply_theme()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        t = ThemeManager.get_theme()
        
        # 설명
        desc_label = QLabel("저장된 번호가 과거 당첨 번호와 일치하는지 확인합니다.")
        desc_label.setStyleSheet(f"color: {t['text_secondary']}; font-size: 14px;")
        layout.addWidget(desc_label)
        
        # 번호 선택
        source_group = QGroupBox("확인할 번호 선택")
        source_layout = QVBoxLayout(source_group)
        
        self.source_combo = QComboBox()
        self.source_combo.addItem("즐겨찾기에서 선택")
        self.source_combo.addItem("히스토리에서 선택")
        self.source_combo.currentIndexChanged.connect(self._update_number_list)
        source_layout.addWidget(self.source_combo)
        
        self.number_list = QListWidget()
        self.number_list.setMaximumHeight(150)
        source_layout.addWidget(self.number_list)
        
        layout.addWidget(source_group)
        
        # 확인 버튼
        check_btn = QPushButton("🔍 당첨 확인 실행")
        check_btn.setMinimumHeight(45)
        check_btn.clicked.connect(self._run_check)
        layout.addWidget(check_btn)
        
        # 결과 영역
        result_group = QGroupBox("확인 결과")
        result_layout = QVBoxLayout(result_group)
        
        self.result_area = QScrollArea()
        self.result_area.setWidgetResizable(True)
        self.result_container = QWidget()
        self.result_inner_layout = QVBoxLayout(self.result_container)
        self.result_inner_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.result_area.setWidget(self.result_container)
        result_layout.addWidget(self.result_area)
        
        layout.addWidget(result_group, 1)
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.setMinimumHeight(40)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        # 초기 데이터 로드
        self._update_number_list()
    
    def _update_number_list(self):
        self.number_list.clear()
        
        if self.source_combo.currentIndex() == 0:
            # 즐겨찾기
            for fav in self.favorites_manager.get_all():
                nums = fav.get('numbers', [])
                memo = fav.get('memo', '')
                text = f"{', '.join(map(str, nums))}"
                if memo:
                    text += f" ({memo})"
                self.number_list.addItem(text)
        else:
            # 히스토리
            for hist in self.history_manager.get_recent(50):
                nums = hist.get('numbers', [])
                text = f"{', '.join(map(str, nums))}"
                self.number_list.addItem(text)
    
    def _run_check(self):
        # 결과 초기화
        while self.result_inner_layout.count():
            item = self.result_inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        t = ThemeManager.get_theme()
        
        # 선택된 번호 가져오기
        row = self.number_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "선택 필요", "확인할 번호를 선택하세요.")
            return
        
        if self.source_combo.currentIndex() == 0:
            data = self.favorites_manager.get_all()
        else:
            data = self.history_manager.get_recent(50)
        
        if row >= len(data):
            return
        
        my_numbers = set(data[row].get('numbers', []))
        
        # 저장된 당첨 데이터로 확인
        winning_data = self.stats_manager.winning_data
        
        if not winning_data:
            no_result = QLabel("확인할 당첨 데이터가 없습니다.\n당첨 정보 위젯에서 회차를 조회해 주세요.")
            no_result.setStyleSheet(f"color: {t['text_muted']}; padding: 20px;")
            no_result.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.result_inner_layout.addWidget(no_result)
            return
        
        found_any = False
        
        for win_data in winning_data:
            draw_no = win_data['draw_no']
            winning_nums = set(win_data['numbers'])
            bonus = win_data['bonus']
            
            matched = my_numbers & winning_nums
            match_count = len(matched)
            bonus_matched = bonus in my_numbers
            
            # 등수 판정
            rank = None
            if match_count == 6:
                rank = 1
            elif match_count == 5 and bonus_matched:
                rank = 2
            elif match_count == 5:
                rank = 3
            elif match_count == 4:
                rank = 4
            elif match_count == 3:
                rank = 5
            
            if match_count >= 3:
                found_any = True
                
                # 결과 행 생성
                result_row = QFrame()
                result_row.setStyleSheet(f"""
                    QFrame {{
                        background-color: {t['bg_secondary']};
                        border: 1px solid {t['border']};
                        border-radius: 8px;
                        padding: 10px;
                    }}
                """)
                row_layout = QVBoxLayout(result_row)
                
                # 회차 및 등수
                header = QHBoxLayout()
                draw_label = QLabel(f"#{draw_no}회")
                draw_label.setStyleSheet(f"font-weight: bold; color: {t['accent']};")
                header.addWidget(draw_label)
                
                if rank:
                    rank_label = QLabel(f"🎉 {rank}등!")
                    rank_colors = {1: '#FF0000', 2: '#FF6600', 3: '#FFCC00', 4: '#00CC00', 5: '#0066CC'}
                    rank_label.setStyleSheet(f"font-weight: bold; color: {rank_colors.get(rank, t['text_primary'])};")
                    header.addWidget(rank_label)
                
                match_label = QLabel(f"일치: {match_count}개" + (" +보너스" if bonus_matched else ""))
                match_label.setStyleSheet(f"color: {t['text_secondary']};")
                header.addWidget(match_label)
                header.addStretch()
                
                row_layout.addLayout(header)
                
                # 번호 비교
                nums_layout = QHBoxLayout()
                nums_layout.addWidget(QLabel("내 번호:"))
                for num in sorted(my_numbers):
                    highlighted = num in matched
                    ball = LottoBall(num, size=28, highlighted=highlighted)
                    nums_layout.addWidget(ball)
                nums_layout.addStretch()
                row_layout.addLayout(nums_layout)
                
                self.result_inner_layout.addWidget(result_row)
        
        if not found_any:
            no_result = QLabel("😢 3개 이상 일치하는 회차가 없습니다.")
            no_result.setStyleSheet(f"color: {t['text_muted']}; padding: 20px;")
            no_result.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.result_inner_layout.addWidget(no_result)
    
    def _apply_theme(self):
        t = ThemeManager.get_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t['bg_primary']};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {t['border']};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: {t['bg_secondary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                padding: 0 8px;
            }}
            QPushButton {{
                background-color: {t['accent']};
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                padding: 10px;
            }}
            QPushButton:hover {{
                background-color: {t['accent_hover']};
            }}
            QComboBox {{
                padding: 8px;
                border: 1px solid {t['border']};
                border-radius: 6px;
                background-color: {t['bg_secondary']};
            }}
            QListWidget {{
                border: 1px solid {t['border']};
                border-radius: 6px;
                background-color: {t['bg_secondary']};
            }}
        """)


# ============================================================
# 데이터 내보내기/가져오기 다이얼로그
# ============================================================
class ExportImportDialog(QDialog):
    """데이터 내보내기/가져오기 다이얼로그"""
    
    def __init__(self, favorites_manager: FavoritesManager, 
                 history_manager, stats_manager: WinningStatsManager, parent=None):
        super().__init__(parent)
        self.favorites_manager = favorites_manager
        self.history_manager = history_manager
        self.stats_manager = stats_manager
        self.setWindowTitle("📁 데이터 내보내기/가져오기")
        self.setMinimumSize(450, 350)
        self._setup_ui()
        self._apply_theme()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        t = ThemeManager.get_theme()
        
        # 내보내기 그룹
        export_group = QGroupBox("📤 내보내기")
        export_layout = QVBoxLayout(export_group)
        
        # 데이터 유형 선택
        data_layout = QHBoxLayout()
        data_layout.addWidget(QLabel("데이터 선택:"))
        self.data_combo = QComboBox()
        self.data_combo.addItems(["즐겨찾기", "히스토리", "당첨 통계"])
        data_layout.addWidget(self.data_combo)
        data_layout.addStretch()
        export_layout.addLayout(data_layout)
        
        # 형식 선택
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("형식:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["CSV", "JSON"])
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        export_layout.addLayout(format_layout)
        
        # 내보내기 버튼
        export_btn = QPushButton("💾 내보내기")
        export_btn.clicked.connect(self._export_data)
        export_layout.addWidget(export_btn)
        
        layout.addWidget(export_group)
        
        # 가져오기 그룹
        import_group = QGroupBox("📥 가져오기")
        import_layout = QVBoxLayout(import_group)
        
        import_desc = QLabel("JSON 파일에서 데이터를 가져옵니다.\n기존 데이터에 병합됩니다.")
        import_desc.setStyleSheet(f"color: {t['text_muted']}; font-size: 12px;")
        import_layout.addWidget(import_desc)
        
        # 가져오기 대상 선택
        import_target_layout = QHBoxLayout()
        import_target_layout.addWidget(QLabel("가져오기 대상:"))
        self.import_combo = QComboBox()
        self.import_combo.addItems(["즐겨찾기", "히스토리"])
        import_target_layout.addWidget(self.import_combo)
        import_target_layout.addStretch()
        import_layout.addLayout(import_target_layout)
        
        import_btn = QPushButton("📂 파일 선택 및 가져오기")
        import_btn.clicked.connect(self._import_data)
        import_layout.addWidget(import_btn)
        
        layout.addWidget(import_group)
        
        layout.addStretch()
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.setMinimumHeight(40)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
    
    def _export_data(self):
        data_type_idx = self.data_combo.currentIndex()
        format_idx = self.format_combo.currentIndex()
        
        # 데이터 가져오기
        if data_type_idx == 0:
            data = self.favorites_manager.get_all()
            data_type = 'favorites'
            default_name = 'lotto_favorites'
        elif data_type_idx == 1:
            data = self.history_manager.get_all()
            data_type = 'history'
            default_name = 'lotto_history'
        else:
            data = self.stats_manager.winning_data
            data_type = 'winning_stats'
            default_name = 'lotto_winning_stats'
        
        if not data:
            QMessageBox.warning(self, "데이터 없음", "내보낼 데이터가 없습니다.")
            return
        
        # 파일 저장 다이럿로그
        if format_idx == 0:
            ext = "csv"
            filter_str = "CSV 파일 (*.csv)"
        else:
            ext = "json"
            filter_str = "JSON 파일 (*.json)"
        
        filepath, _ = QFileDialog.getSaveFileName(
            self, "내보내기", f"{default_name}.{ext}", filter_str
        )
        
        if not filepath:
            return
        
        # 내보내기 실행
        success = False
        if format_idx == 0:
            success = DataExporter.export_to_csv(data, filepath, data_type)
        else:
            success = DataExporter.export_to_json(data, filepath)
        
        if success:
            QMessageBox.information(self, "완료", f"{len(data)}개 항목이 저장되었습니다.\n{filepath}")
        else:
            QMessageBox.warning(self, "오류", "내보내기에 실패했습니다.")
    
    def _import_data(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "가져오기", "", "JSON 파일 (*.json)"
        )
        
        if not filepath:
            return
        
        data = DataExporter.import_from_json(filepath)
        
        if data is None:
            QMessageBox.warning(self, "오류", "파일을 읽는데 실패했습니다.")
            return
        
        target_idx = self.import_combo.currentIndex()
        imported_count = 0
        
        if target_idx == 0:
            # 즐겨찾기에 추가
            for item in data:
                if 'numbers' in item:
                    if self.favorites_manager.add(item['numbers'], item.get('memo', '')):
                        imported_count += 1
        else:
            # 히스토리에 추가
            for item in data:
                if 'numbers' in item:
                    if self.history_manager.add(item['numbers']):
                        imported_count += 1
        
        QMessageBox.information(
            self, "완료", 
            f"{imported_count}개 항목이 가져와졌습니다.\n(중복 항목은 제외됨)"
        )
    
    def _apply_theme(self):
        t = ThemeManager.get_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t['bg_primary']};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {t['border']};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: {t['bg_secondary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                padding: 0 8px;
            }}
            QPushButton {{
                background-color: {t['accent']};
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                padding: 10px;
            }}
            QPushButton:hover {{
                background-color: {t['accent_hover']};
            }}
            QComboBox {{
                padding: 8px;
                border: 1px solid {t['border']};
                border-radius: 6px;
                background-color: {t['bg_secondary']};
            }}
        """)


# ============================================================
# 메인 애플리케이션
# ============================================================
class LottoApp(QWidget):
    def __init__(self):
        super().__init__()
        self.generated_sets: List[List[int]] = []
        self.favorites_manager = FavoritesManager()
        self.history_manager = HistoryManager()  # 히스토리 관리
        self.stats_manager = WinningStatsManager()  # 당첨 통계 관리
        self.smart_generator = SmartNumberGenerator(self.stats_manager)  # 스마트 생성기
        self.total_generated = 0
        self.last_generated_time: Optional[datetime.datetime] = None
        
        ThemeManager.add_listener(self._on_theme_changed)
        
        self.initUI()
        self._setup_shortcuts()
        logger.info("Application started")
    
    def initUI(self):
        self.setWindowTitle(f"{APP_CONFIG['APP_NAME']} v{APP_CONFIG['VERSION']}")
        self.setGeometry(300, 200, *APP_CONFIG['WINDOW_SIZE'])
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(25, 20, 25, 10)
        
        # 상단 헤더
        header_layout = QHBoxLayout()
        
        title_label = QLabel('Lotto 6/45 Generator')
        title_label.setFont(QFont('Malgun Gothic', 22, QFont.Weight.Bold))
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # 테마 토글 버튼
        self.theme_btn = QPushButton("🌙 Dark")
        self.theme_btn.setFixedSize(80, 32)
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.setToolTip("다크모드 전환 (Ctrl+D)")
        self.theme_btn.clicked.connect(self._toggle_theme)
        header_layout.addWidget(self.theme_btn)
        
        # 통계 버튼
        self.stats_btn = QPushButton("📊 통계")
        self.stats_btn.setFixedSize(70, 32)
        self.stats_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stats_btn.setToolTip("번호 통계 보기")
        self.stats_btn.clicked.connect(self._show_statistics)
        header_layout.addWidget(self.stats_btn)
        
        # 히스토리 버튼
        self.history_btn = QPushButton("📜 히스토리")
        self.history_btn.setFixedSize(90, 32)
        self.history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_btn.setToolTip("생성 히스토리 보기")
        self.history_btn.clicked.connect(self._show_history)
        header_layout.addWidget(self.history_btn)
        
        # 즐겨찾기 버튼
        self.fav_btn = QPushButton("⭐ 즐겨찾기")
        self.fav_btn.setFixedSize(85, 32)
        self.fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fav_btn.setToolTip("즐겨찾기 보기")
        self.fav_btn.clicked.connect(self._show_favorites)
        header_layout.addWidget(self.fav_btn)
        
        # 실제 통계 버튼

        self.real_stats_btn = QPushButton("📈 실제통계")
        self.real_stats_btn.setFixedSize(85, 32)
        self.real_stats_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.real_stats_btn.setToolTip("실제 당첨 번호 통계")
        self.real_stats_btn.clicked.connect(self._show_real_stats)
        header_layout.addWidget(self.real_stats_btn)
        
        # 당첨 확인 버튼
        self.winning_check_btn = QPushButton("🎯 당첨확인")
        self.winning_check_btn.setFixedSize(85, 32)
        self.winning_check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.winning_check_btn.setToolTip("과거 당첨 확인")
        self.winning_check_btn.clicked.connect(self._show_winning_check)
        header_layout.addWidget(self.winning_check_btn)
        
        # 내보내기 버튼
        self.export_btn = QPushButton("📁")
        self.export_btn.setFixedSize(40, 32)
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.setToolTip("데이터 내보내기/가져오기")
        self.export_btn.clicked.connect(self._show_export_import)
        header_layout.addWidget(self.export_btn)
        
        main_layout.addLayout(header_layout)
        
        # 당첨 정보 위젯
        self.winning_info_widget = WinningInfoWidget()
        self.winning_info_widget.dataLoaded.connect(self._on_winning_data_loaded)
        main_layout.addWidget(self.winning_info_widget)
        
        # 설정 영역
        self.settings_group = QGroupBox("생성 옵션")
        settings_layout = QGridLayout()
        settings_layout.setVerticalSpacing(12)
        settings_layout.setHorizontalSpacing(15)
        settings_layout.setContentsMargins(15, 20, 15, 15)
        
        label_style = "font-size: 14px; font-weight: bold;"
        input_height = 32
        
        # 세트 수
        lbl_sets = QLabel("세트 수")
        lbl_sets.setStyleSheet(label_style)
        self.num_sets_spinbox = QSpinBox()
        self.num_sets_spinbox.setRange(1, APP_CONFIG['MAX_SETS'])
        self.num_sets_spinbox.setValue(5)
        self.num_sets_spinbox.setFixedWidth(80)
        self.num_sets_spinbox.setFixedHeight(input_height)
        self.num_sets_spinbox.setToolTip("생성할 번호 세트 수 (1-20)")
        settings_layout.addWidget(lbl_sets, 0, 0)
        settings_layout.addWidget(self.num_sets_spinbox, 0, 1)
        
        # 고정수
        lbl_fixed = QLabel("고정수")
        lbl_fixed.setStyleSheet(label_style)
        self.fixed_nums_input = QLineEdit()
        self.fixed_nums_input.setPlaceholderText("예: 1, 7, 13 (최대 5개)")
        self.fixed_nums_input.setFixedHeight(input_height)
        self.fixed_nums_input.setToolTip("반드시 포함할 번호를 쉼표로 구분하여 입력")
        settings_layout.addWidget(lbl_fixed, 0, 2)
        settings_layout.addWidget(self.fixed_nums_input, 0, 3)
        
        # 제외수
        lbl_exclude = QLabel("제외수")
        lbl_exclude.setStyleSheet(label_style)
        self.exclude_nums_input = QLineEdit()
        self.exclude_nums_input.setPlaceholderText("예: 4, 13, 44")
        self.exclude_nums_input.setFixedHeight(input_height)
        self.exclude_nums_input.setToolTip("제외할 번호를 쉼표로 구분하여 입력")
        settings_layout.addWidget(lbl_exclude, 1, 0)
        settings_layout.addWidget(self.exclude_nums_input, 1, 1)
        
        # 연속수 제한
        lbl_consecutive = QLabel("연속수 제한")
        lbl_consecutive.setStyleSheet(label_style)
        
        consecutive_layout = QHBoxLayout()
        consecutive_layout.setContentsMargins(0, 0, 0, 0)
        consecutive_layout.setSpacing(8)
        
        self.chk_consecutive = QCheckBox("사용")
        self.chk_consecutive.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_consecutive.setToolTip("연속된 숫자 제한 여부")
        
        self.spin_consecutive = QSpinBox()
        self.spin_consecutive.setRange(2, 6)
        self.spin_consecutive.setValue(3)
        self.spin_consecutive.setFixedWidth(80)
        self.spin_consecutive.setFixedHeight(input_height)
        self.spin_consecutive.setEnabled(False)
        self.spin_consecutive.setToolTip("연속 허용 개수")
        
        self.chk_consecutive.toggled.connect(lambda c: self.spin_consecutive.setEnabled(c))
        
        consecutive_layout.addWidget(self.chk_consecutive)
        consecutive_layout.addWidget(self.spin_consecutive)
        consecutive_layout.addWidget(QLabel("개 이상 제외"))
        consecutive_layout.addStretch()
        
        settings_layout.addWidget(lbl_consecutive, 1, 2)
        settings_layout.addLayout(consecutive_layout, 1, 3)
        
        # 당첨번호 비교
        self.chk_compare = QCheckBox("지난 당첨번호와 비교")
        self.chk_compare.setToolTip("생성된 번호를 현재 조회된 당첨번호와 비교합니다")
        settings_layout.addWidget(self.chk_compare, 2, 0, 1, 2)
        
        # 스마트 생성 옵션
        self.chk_smart_gen = QCheckBox("🧠 스마트 생성 (통계 기반)")
        self.chk_smart_gen.setToolTip("과거 당첨 통계를 기반으로 번호를 생성합니다")
        settings_layout.addWidget(self.chk_smart_gen, 2, 2, 1, 2)
        
        self.settings_group.setLayout(settings_layout)
        main_layout.addWidget(self.settings_group)
        
        # 결과 영역
        self.result_area = QScrollArea()
        self.result_area.setWidgetResizable(True)
        self.result_area.setFrameShape(QFrame.Shape.NoFrame)
        
        self.result_container = QWidget()
        self.result_layout = QVBoxLayout(self.result_container)
        self.result_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.result_layout.setSpacing(0)
        self.result_layout.setContentsMargins(0, 0, 0, 0)
        
        # Placeholder
        self.placeholder_label = QLabel("'번호 생성' 버튼을 클릭하여 행운의 번호를 받아보세요!")
        self.placeholder_label.setObjectName("placeholderLabel")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_layout.addWidget(self.placeholder_label)
        
        self.result_area.setWidget(self.result_container)
        main_layout.addWidget(self.result_area, 1)
        
        # 버튼 영역
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        btn_height = 45
        
        self.generate_btn = QPushButton('[G] 번호 생성')
        self.generate_btn.setObjectName("generateBtn")
        self.generate_btn.setMinimumHeight(btn_height)
        self.generate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.generate_btn.setToolTip("새 번호 생성 (Ctrl+G)")
        self.generate_btn.clicked.connect(self.generate_numbers)
        
        self.clear_btn = QPushButton('[R] 초기화')
        self.clear_btn.setObjectName("clearBtn")
        self.clear_btn.setMinimumHeight(btn_height)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setToolTip("결과 초기화 (Ctrl+R)")
        self.clear_btn.clicked.connect(self.clear_results)
        
        self.save_btn = QPushButton('[S] 저장')
        self.save_btn.setObjectName("saveBtn")
        self.save_btn.setMinimumHeight(btn_height)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setToolTip("파일로 저장 (Ctrl+S)")
        self.save_btn.clicked.connect(self.save_file)
        self.save_btn.setEnabled(False)
        
        self.copy_btn = QPushButton('[C] 복사')
        self.copy_btn.setObjectName("copyBtn")
        self.copy_btn.setMinimumHeight(btn_height)
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.setToolTip("클립보드에 복사 (Ctrl+C)")
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        self.copy_btn.setEnabled(False)
        
        btn_layout.addWidget(self.generate_btn, 2)
        btn_layout.addWidget(self.clear_btn, 1)
        btn_layout.addWidget(self.save_btn, 1)
        btn_layout.addWidget(self.copy_btn, 1)
        
        main_layout.addLayout(btn_layout)
        
        # 상태바
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("준비됨")
        main_layout.addWidget(self.status_bar)
        
        self.setLayout(main_layout)
        self._apply_theme()
    
    def _setup_shortcuts(self):
        """키보드 단축키 설정"""
        shortcuts = [
            (QKeySequence("Ctrl+G"), self.generate_numbers),
            (QKeySequence("Ctrl+R"), self.clear_results),
            (QKeySequence("Ctrl+S"), self.save_file),
            (QKeySequence("Ctrl+D"), self._toggle_theme),
        ]
        for key, callback in shortcuts:
            shortcut = QShortcut(key, self)
            shortcut.activated.connect(callback)
    
    def _toggle_theme(self):
        ThemeManager.toggle_theme()
        self.theme_btn.setText("Light" if ThemeManager.get_theme_name() == 'dark' else "Dark")
    
    def _on_theme_changed(self):
        self._apply_theme()
        # 자식 위젯들도 테마 적용
        self.winning_info_widget._apply_theme()
        if self.winning_info_widget.current_data:
            self.winning_info_widget._on_data_received(self.winning_info_widget.current_data)
    
    def _apply_theme(self):
        """전체 테마 적용"""
        self.setStyleSheet(ThemeManager.get_stylesheet())
        t = ThemeManager.get_theme()
        is_dark = ThemeManager.get_theme_name() == 'dark'
        
        # 헤더 버튼 스타일 - 아이콘 스타일
        header_btn_style = f"""
            QPushButton {{
                background-color: {t['bg_tertiary']};
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: bold;
                color: {t['text_secondary']};
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: {t['accent_light']};
                color: {t['accent']};
            }}
        """
        self.theme_btn.setStyleSheet(header_btn_style)
        self.theme_btn.setText("☀️ Light" if is_dark else "🌙 Dark")
        
        # 통계/히스토리 버튼 스타일
        self.stats_btn.setStyleSheet(header_btn_style)
        self.history_btn.setStyleSheet(header_btn_style)
        
        # 즐겨찾기 버튼
        fav_btn_style = f"""
            QPushButton {{
                background-color: {t['warning_light']};
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: bold;
                color: {t['warning']};
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: {t['warning']};
                color: white;
            }}
        """
        self.fav_btn.setStyleSheet(fav_btn_style)
        self.fav_btn.setText("⭐ 즐겨찾기")
        
        # 결과 컨테이너 스타일
        self.result_container.setStyleSheet(f"""
            background-color: {t['bg_secondary']};
            border-radius: 10px;
        """)
        
        # 설정 그룹박스 스타일 (더 세련되게)
        self.settings_group.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {t['border']};
                border-radius: 10px;
                margin-top: 14px;
                padding-top: 8px;
                background-color: {t['bg_secondary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 3px 12px;
                left: 12px;
                background-color: {t['accent']};
                color: white;
                border-radius: 5px;
                font-size: 13px;
            }}
        """)
    
    def _show_favorites(self):
        dialog = FavoritesDialog(self.favorites_manager, self)
        dialog.exec()
    
    def _on_winning_data_loaded(self, data: dict):
        """당첨 데이터 로드 완료 시"""
        self.status_bar.showMessage(f"당첨 정보 로드 완료: {data.get('drwNo')}회")
        
        # 통계에 당첨 데이터 저장
        try:
            draw_no = data.get('drwNo')
            numbers = [data.get(f'drwtNo{i}') for i in range(1, 7)]
            bonus = data.get('bnusNo')
            if draw_no and all(numbers) and bonus:
                self.stats_manager.add_winning_data(draw_no, numbers, bonus)
        except Exception as e:
            logger.error(f"Failed to save winning data: {e}")
    
    def _add_to_favorites(self, numbers: List[int]):
        """즐겨찾기에 추가"""
        if self.favorites_manager.add(numbers):
            self.status_bar.showMessage(f"⭐ 즐겨찾기에 추가됨: {numbers}")
        else:
            self.status_bar.showMessage("⚠️ 이미 즐겨찾기에 있습니다")
    
    def _on_row_copied(self, numbers: List[int]):
        """개별 행 복사 시 피드백"""
        nums_str = " ".join(f"{n:02d}" for n in numbers)
        self.status_bar.showMessage(f"📋 복사됨: {nums_str}")
    
    def _show_statistics(self):
        """통계 다이얼로그 표시"""
        dialog = StatisticsDialog(self.history_manager, self)
        dialog.exec()
    
    def _show_history(self):
        """히스토리 다이얼로그 표시"""
        dialog = HistoryDialog(self.history_manager, self)
        dialog.exec()
    
    def _show_real_stats(self):
        """실제 당첨 통계 다이얼로그 표시"""
        dialog = RealStatsDialog(self.stats_manager, self)
        dialog.exec()
    
    def _show_winning_check(self):
        """당첨 확인 다이얼로그 표시"""
        dialog = WinningCheckDialog(
            self.favorites_manager, 
            self.history_manager, 
            self.stats_manager, 
            self
        )
        dialog.exec()
    
    def _show_export_import(self):
        """내보내기/가져오기 다이얼로그 표시"""
        dialog = ExportImportDialog(
            self.favorites_manager,
            self.history_manager,
            self.stats_manager,
            self
        )
        dialog.exec()
    
    def parse_input_numbers(self, text: str) -> Tuple[Set[int], List[str]]:
        """입력값 파싱 및 검증 - 범위 입력 지원 (예: 1-10, 20, 30-35)"""
        if not text.strip():
            return set(), []
        
        errors = []
        valid_nums = set()
        
        # 다양한 구분자 지원: 쉼표, 공백, 세미콜론
        import re
        # 연속된 구분자는 하나로 처리
        parts = re.split(r'[,;\s]+', text.strip())
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # 범위 표기 체크 (예: 1-10)
            if '-' in part and not part.startswith('-'):
                # 1-10-20 같은 잘못된 형식 체크
                if part.count('-') > 1:
                    errors.append(f"'{part}' 잘못된 범위 형식입니다")
                    continue
                    
                range_match = re.match(r'^(\d+)-(\d+)$', part)
                if range_match:
                    start, end = int(range_match.group(1)), int(range_match.group(2))
                    
                    if start > end:
                        start, end = end, start  # 순서 정정
                        
                    if start < 1 or end > 45:
                        errors.append(f"'{part}' 범위가 1-45를 벗어났습니다")
                    else:
                        for num in range(start, end + 1):
                            valid_nums.add(num)
                else:
                    errors.append(f"'{part}' 유효한 범위 형식이 아닙니다")
                continue
            
            # 단일 숫자
            try:
                # 숫자 외 문자가 섞여있는지 체크
                if not part.isdigit():
                     errors.append(f"'{part}'은(는) 숫자가 아닙니다")
                     continue
                     
                num = int(part)
                if 1 <= num <= 45:
                    valid_nums.add(num)
                else:
                    errors.append(f"'{num}'은(는) 1-45 범위를 벗어났습니다")
            except ValueError:
                errors.append(f"'{part}'은(는) 유효한 숫자가 아닙니다")
        
        return valid_nums, errors
    
    def clear_results(self):
        self.generated_sets.clear()
        while self.result_layout.count():
            child = self.result_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        self.placeholder_label = QLabel("'번호 생성' 버튼을 클릭하여 행운의 번호를 받아보세요!")
        self.placeholder_label.setObjectName("placeholderLabel")
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_layout.addWidget(self.placeholder_label)
        
        self.save_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)
        self.status_bar.showMessage("초기화됨")
    
    def has_consecutive(self, numbers: List[int], limit: int) -> bool:
        if len(numbers) < limit:
            return False
        sorted_nums = sorted(numbers)
        consecutive_count = 1
        for i in range(len(sorted_nums) - 1):
            if sorted_nums[i] + 1 == sorted_nums[i+1]:
                consecutive_count += 1
                if consecutive_count >= limit:
                    return True
            else:
                consecutive_count = 1
        return False
    
    def generate_numbers(self):
        fixed_nums, fixed_errors = self.parse_input_numbers(self.fixed_nums_input.text())
        exclude_nums, exclude_errors = self.parse_input_numbers(self.exclude_nums_input.text())
        
        # 에러 체크
        all_errors = fixed_errors + exclude_errors
        if all_errors:
            QMessageBox.warning(self, "입력 오류", "\n".join(all_errors))
            return
        
        if len(fixed_nums) > APP_CONFIG['MAX_FIXED_NUMS']:
            QMessageBox.warning(self, "오류", f"고정수는 {APP_CONFIG['MAX_FIXED_NUMS']}개까지만 가능합니다.")
            return
        
        if fixed_nums & exclude_nums:
            overlap = fixed_nums & exclude_nums
            QMessageBox.warning(self, "오류", f"고정수와 제외수에 중복된 번호가 있습니다: {overlap}")
            return
        
        available_count = 45 - len(exclude_nums) - len(fixed_nums)
        if available_count < (6 - len(fixed_nums)):
            QMessageBox.warning(self, "오류", "생성 가능한 번호가 부족합니다.")
            return
        
        check_consecutive = self.chk_consecutive.isChecked()
        consecutive_limit = self.spin_consecutive.value()
        
        if check_consecutive and self.has_consecutive(list(fixed_nums), consecutive_limit):
            QMessageBox.warning(self, "오류", f"고정수에 이미 {consecutive_limit}개 이상의 연속된 숫자가 포함되어 있습니다.")
            return
        
        # 결과 영역 초기화
        self.clear_results()
        self.placeholder_label.setVisible(False)
        
        # 비교할 당첨 번호 가져오기
        compare_mode = self.chk_compare.isChecked()
        winning_numbers, bonus_number = [], 0
        if compare_mode:
            winning_numbers, bonus_number = self.winning_info_widget.get_winning_numbers()
        
        full_pool = set(range(1, 46))
        available_pool = list(full_pool - exclude_nums - fixed_nums)
        num_sets = self.num_sets_spinbox.value()
        
        generated_count = 0
        max_retries = 1000
        
        use_smart = self.chk_smart_gen.isChecked()
        
        while generated_count < num_sets:
            retry_count = 0
            valid_set_found = False
            current_set = []
            
            while retry_count < max_retries:
                if use_smart:
                    # 스마트 생성 (전략: 핫 넘버 우선 + 균형)
                    # 다양성을 위해 세트마다 전략을 조금씩 변경
                    prefer_hot = (generated_count % 4 != 3)  # 4번 중 3번은 핫 넘버, 1번은 콜드 넘버
                    
                    temp_set = self.smart_generator.generate_smart_numbers(
                        fixed_nums=fixed_nums,
                        exclude_nums=exclude_nums,
                        prefer_hot=prefer_hot,
                        balance_mode=True
                    )
                else:
                    # 일반 랜덤 생성
                    temp_set = list(fixed_nums)
                    needed = 6 - len(temp_set)
                    temp_set.extend(random.sample(available_pool, needed))
                
                if check_consecutive and self.has_consecutive(temp_set, consecutive_limit):
                    retry_count += 1
                    continue
                
                current_set = sorted(temp_set)
                valid_set_found = True
                break
            
            if not valid_set_found:
                QMessageBox.warning(self, "실패", "조건이 너무 까다로워 번호를 생성할 수 없습니다.\n설정을 변경해주세요.")
                return
            
            self.generated_sets.append(current_set)
            
            # 히스토리에 저장
            self.history_manager.add(current_set)
            
            # 분석
            analysis = NumberAnalyzer.analyze(current_set)
            
            # 비교
            matched = []
            if compare_mode and winning_numbers:
                comparison = NumberAnalyzer.compare_with_winning(current_set, winning_numbers, bonus_number)
                matched = comparison.get('matched', [])
            
            row = ResultRow(generated_count + 1, current_set, analysis, matched)
            row.favoriteClicked.connect(self._add_to_favorites)
            row.copyClicked.connect(self._on_row_copied)
            self.result_layout.addWidget(row)
            generated_count += 1
        
        self.total_generated += num_sets
        self.last_generated_time = datetime.datetime.now()
        
        self.save_btn.setEnabled(True)
        self.copy_btn.setEnabled(True)
        
        self.status_bar.showMessage(f"✅ {num_sets}개 세트 생성 완료 (총 {self.total_generated}개)")
        logger.info(f"Generated {num_sets} sets")
    
    def _get_text_data(self) -> str:
        lines = []
        for i, nums in enumerate(self.generated_sets):
            nums_str = " ".join(f"{n:02d}" for n in nums)
            analysis = NumberAnalyzer.analyze(nums)
            lines.append(f"{i+1}. {nums_str}  (합계:{analysis['total']}, 홀:{analysis['odd']} 짝:{analysis['even']})")
        return "\n".join(lines)
    
    def save_file(self):
        if not self.generated_sets:
            return
        # 기본 파일명 제안
        default_name = datetime.datetime.now().strftime("로또번호_%Y%m%d_%H%M%S.txt")
        path, _ = QFileDialog.getSaveFileName(self, "저장", default_name, "텍스트 (*.txt)")
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"═══ 로또 번호 ({now}) ═══\n\n")
                    f.write(self._get_text_data())
                    f.write(f"\n\n생성: {APP_CONFIG['APP_NAME']} v{APP_CONFIG['VERSION']}")
                self.status_bar.showMessage(f"저장 완료: {path}")
                logger.info(f"Saved to {path}")
            except Exception as e:
                logger.error(f"Save failed: {e}")
                QMessageBox.critical(self, "오류", str(e))
    
    def copy_to_clipboard(self):
        if not self.generated_sets:
            return
        QApplication.clipboard().setText(self._get_text_data())
        self.status_bar.showMessage("📋 클립보드에 복사됨")
    
    def closeEvent(self, event):
        """앱 종료 시 리소스 정리"""
        logger.info("Application closing...")
        
        # API 요청 취소
        if hasattr(self.winning_info_widget, 'network_manager'):
            self.winning_info_widget.network_manager.cancel()
        
        event.accept()


# ============================================================
# 메인 엔트리 포인트
# ============================================================
def exception_hook(exctype, value, traceback):
    """Global exception handler to ensure crashes are reported"""
    logger.critical("Uncaught exception", exc_info=(exctype, value, traceback))
    sys.__excepthook__(exctype, value, traceback)
    
    # GUI가 이미 생성되었는지 확인
    if QApplication.instance():
        error_msg = f"{value}\n\n로그 파일을 확인해주세요."
        QMessageBox.critical(None, "Critical Error", f"예기치 않은 오류가 발생했습니다:\n{error_msg}")

def main():
    sys.excepthook = exception_hook
    
    app = QApplication(sys.argv)
    
    # 폰트 설정
    font = QFont("Malgun Gothic", 10)
    app.setFont(font)
    
    window = LottoApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
