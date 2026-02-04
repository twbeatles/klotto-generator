from pathlib import Path
import sys

# ============================================================
# PyInstaller 번들 경로 처리
# ============================================================
def _get_base_path() -> Path:
    """PyInstaller 번들 또는 개발 환경의 기본 경로 반환"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 번들 (onefile 모드)
        return Path(sys._MEIPASS)
    else:
        # 개발 환경
        return Path(__file__).resolve().parent.parent

def _get_db_path() -> Path:
    """DB 경로 결정: 번들에 있으면 사용자 데이터 폴더로 복사 후 사용"""
    base = _get_base_path()
    bundled_db = base / "data" / "lotto_history.db"
    user_db = Path.home() / ".lotto_generator" / "lotto_history.db"
    
    # 번들에 DB가 있고 사용자 폴더에 없으면 복사
    if bundled_db.exists() and not user_db.exists():
        try:
            user_db.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(bundled_db, user_db)
        except Exception:
            pass
    
    # 사용자 폴더의 DB 우선, 없으면 번들/개발 경로
    if user_db.exists():
        return user_db
    elif bundled_db.exists():
        return bundled_db
    else:
        # 개발 환경에서 data 폴더 경로
        return Path(__file__).resolve().parent.parent / "data" / "lotto_history.db"

# ============================================================
# 상수 정의
# ============================================================
APP_CONFIG = {
    'APP_NAME': 'Lotto 6/45 Generator Pro',
    'VERSION': '2.5',
    'WINDOW_SIZE': (680, 980),
    'FAVORITES_FILE': Path.home() / ".lotto_generator" / "favorites.json",
    'HISTORY_FILE': Path.home() / ".lotto_generator" / "history.json",
    'WINNING_STATS_FILE': Path.home() / ".lotto_generator" / "winning_stats.json",
    'LOTTO_HISTORY_DB': _get_db_path(),
    'MAX_SETS': 20,
    'MAX_FIXED_NUMS': 5,
    'OPTIMAL_SUM_RANGE': (100, 175),
    'API_TIMEOUT': 10,
    'MAX_HISTORY': 500,
    'WINNING_STATS_CACHE_SIZE': 100,
}

LOTTO_COLORS = {
    '1-10': {'bg': '#FBC400', 'text': 'black', 'gradient': '#FFD700'},
    '11-20': {'bg': '#2980B9', 'text': 'white', 'gradient': '#3498DB'},
    '21-30': {'bg': '#C0392B', 'text': 'white', 'gradient': '#E74C3C'},
    '31-40': {'bg': '#7F8C8D', 'text': 'white', 'gradient': '#95A5A6'},
    '41-45': {'bg': '#27AE60', 'text': 'white', 'gradient': '#2ECC71'},
}

DHLOTTERY_API_URL = "https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do?srchLtEpsd={}"

THEMES = {
    'light': {
        'name': '라이트',
        'bg_primary': '#FFFFFF',          # Pure white for modern feel
        'bg_secondary': '#F7F9FC',        # Very light cool gray
        'bg_tertiary': '#EDF1F7',         # Slightly darker for inputs/cards
        'bg_hover': '#E4E9F2',
        'text_primary': '#222B45',        # Deep navy, almost black
        'text_secondary': '#8F9BB3',      # Cool gray
        'text_muted': '#C5CEE0',
        'border': '#E4E9F2',
        'border_light': '#EDF1F7',
        'accent': '#3366FF',              # Vibrant blue
        'accent_hover': '#274BDB',
        'accent_light': '#D6E4FF',        # Very light blue for backgrounds
        'success': '#00D68F',             # Vibrant green
        'success_light': '#DBF9ED',
        'warning': '#FFAA00',
        'warning_light': '#FFF5DB',
        'danger': '#FF3D71',
        'danger_light': '#FFD6D9',
        'neutral': '#8F9BB3',
        'shadow': 'rgba(44, 51, 73, 0.1)',
        'shadow_medium': 'rgba(44, 51, 73, 0.2)',
        'glow': 'rgba(51, 102, 255, 0.3)',
        'card_bg': '#FFFFFF',
        'result_row_alt': '#F7F9FC',
    },
    'dark': {
        'name': '다크',
        'bg_primary': '#192038',          # Deep blue-gray
        'bg_secondary': '#222B45',        # Card background
        'bg_tertiary': '#2E3A59',         # Input background
        'bg_hover': '#3D4D75',
        'text_primary': '#FFFFFF',
        'text_secondary': '#8F9BB3',
        'text_muted': '#586582',
        'border': '#2E3A59',
        'border_light': '#252F4F',
        'accent': '#3366FF',              # Same vibrant blue
        'accent_hover': '#598BFF',        # Lighter on hover for dark mode
        'accent_light': '#1A2138',        # Dark tone
        'success': '#00D68F',
        'success_light': '#00422D',
        'warning': '#FFAA00',
        'warning_light': '#4D3400',
        'danger': '#FF3D71',
        'danger_light': '#4D1222',
        'neutral': '#596987',
        'shadow': 'rgba(0, 0, 0, 0.4)',
        'shadow_medium': 'rgba(0, 0, 0, 0.6)',
        'glow': 'rgba(51, 102, 255, 0.4)',
        'card_bg': '#222B45',
        'result_row_alt': '#1F2640',
    }
}
