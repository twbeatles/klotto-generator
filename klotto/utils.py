import sys
import logging
from typing import Dict, List
from .config import THEMES

# ============================================================
# 로깅 설정
# ============================================================
def setup_logging():
    """로깅 시스템 초기화"""
    logger = logging.getLogger("LottoGen")
    logger.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 파일 핸들러 (선택사항 - 필요시 추가)
    # file_handler = logging.FileHandler("lotto_gen.log", encoding='utf-8')
    # file_handler.setFormatter(formatter)
    # logger.addHandler(file_handler)
    
    return logger

logger = setup_logging()

# ============================================================
# 테마 시스템
# ============================================================
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
