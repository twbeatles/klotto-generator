from typing import Dict

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel

from klotto.config import LOTTO_COLORS


class LottoBall(QLabel):
    """개별 로또 번호를 원형 공 모양으로 표시하는 위젯 - 3D 스타일"""

    def __init__(self, number: int, size: int = 40, highlighted: bool = False):
        super().__init__(str(number))
        self.number = number
        self._size = size
        self._highlighted = highlighted
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        font_size = max(11, size // 3)
        self.setFont(QFont("Segoe UI", font_size, QFont.Weight.Bold))
        self.update_style()

    def get_color_info(self) -> Dict:
        if 1 <= self.number <= 10:
            return LOTTO_COLORS["1-10"]
        if self.number <= 20:
            return LOTTO_COLORS["11-20"]
        if self.number <= 30:
            return LOTTO_COLORS["21-30"]
        if self.number <= 40:
            return LOTTO_COLORS["31-40"]
        return LOTTO_COLORS["41-45"]

    def update_style(self):
        colors = self.get_color_info()
        bg = colors["bg"]
        text = colors["text"]
        gradient = colors["gradient"]

        if self._highlighted:
            border_style = "3px solid #FFD700"
            style = f"""
                QLabel {{
                    background: qradialgradient(cx:0.3, cy:0.3, radius:0.8, fx:0.2, fy:0.2,
                        stop:0 {gradient}, stop:0.4 {bg}, stop:1 {bg});
                    color: {text};
                    border-radius: {self._size // 2}px;
                    border: {border_style};
                }}
            """
        else:
            style = f"""
                QLabel {{
                    background: qradialgradient(cx:0.35, cy:0.25, radius:0.9, fx:0.25, fy:0.15,
                        stop:0 {gradient}, stop:0.5 {bg}, stop:1 {self._darken_color(bg, 15)});
                    color: {text};
                    border-radius: {self._size // 2}px;
                    border: 1px solid {self._darken_color(bg, 20)};
                }}
            """

        self.setStyleSheet(style)

    def _darken_color(self, hex_color: str, percent: int) -> str:
        try:
            hex_color = hex_color.lstrip("#")
            r = max(0, int(hex_color[0:2], 16) - percent * 255 // 100)
            g = max(0, int(hex_color[2:4], 16) - percent * 255 // 100)
            b = max(0, int(hex_color[4:6], 16) - percent * 255 // 100)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color

    def set_highlighted(self, highlighted: bool):
        self._highlighted = highlighted
        self.update_style()
