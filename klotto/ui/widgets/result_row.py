from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from klotto.ui.theme import ThemeManager
from klotto.ui.widgets.lotto_ball import LottoBall


class ResultRow(QWidget):
    """하나의 로또 세트(6개 번호)를 표시하는 행 - 개선된 UX"""

    favoriteClicked = pyqtSignal(list)
    copyClicked = pyqtSignal(list)

    def __init__(
        self,
        index: int,
        numbers: List[int],
        analysis: Optional[Dict[str, Any]] = None,
        matched_numbers: Optional[List[int]] = None,
    ):
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

        theme = ThemeManager.get_theme()

        idx_label = QLabel(f"{index}")
        idx_label.setFixedSize(28, 28)
        idx_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        idx_label.setStyleSheet(
            f"""
            QLabel {{
                background-color: {theme['accent_light']};
                color: {theme['accent']};
                font-weight: bold;
                font-size: 12px;
                border-radius: 14px;
            }}
        """
        )
        layout.addWidget(idx_label)

        self.balls = []
        for number in self.numbers:
            highlighted = number in self.matched_numbers
            ball = LottoBall(number, size=36, highlighted=highlighted)
            self.balls.append(ball)
            layout.addWidget(ball)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setStyleSheet(f"background-color: {theme['border']}; max-width: 1px;")
        separator.setFixedHeight(24)
        layout.addWidget(separator)

        if self.analysis:
            total = self.analysis.get("total", 0)
            odd = self.analysis.get("odd", 0)
            even = self.analysis.get("even", 0)
            sum_color = theme["success"] if 100 <= total <= 175 else theme["text_muted"]

            analysis_widget = QWidget()
            analysis_layout = QHBoxLayout(analysis_widget)
            analysis_layout.setContentsMargins(0, 0, 0, 0)
            analysis_layout.setSpacing(8)

            sum_label = QLabel(f"합 {total}")
            sum_label.setStyleSheet(f"color: {sum_color}; font-size: 12px; font-weight: bold;")
            analysis_layout.addWidget(sum_label)

            ratio_label = QLabel(f"홀{odd}:짝{even}")
            ratio_label.setStyleSheet(f"color: {theme['text_muted']}; font-size: 11px;")
            analysis_layout.addWidget(ratio_label)

            layout.addWidget(analysis_widget)

        layout.addStretch()

        if self.matched_numbers:
            match_count = len(self.matched_numbers)
            match_label = QLabel(f"✓ {match_count}")
            match_label.setFixedSize(36, 24)
            match_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            match_label.setStyleSheet(
                f"""
                QLabel {{
                    background-color: {theme['success_light']};
                    color: {theme['success']};
                    font-weight: bold;
                    font-size: 12px;
                    border-radius: 12px;
                }}
            """
            )
            match_label.setToolTip(f"{match_count}개 번호 일치")
            layout.addWidget(match_label)

        copy_btn = QPushButton("📋")
        copy_btn.setFixedSize(28, 28)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                font-size: 14px;
                border-radius: 14px;
            }}
            QPushButton:hover {{
                background: {theme['bg_tertiary']};
            }}
        """
        )
        copy_btn.setToolTip("이 번호 복사")
        copy_btn.clicked.connect(self._copy_numbers)
        layout.addWidget(copy_btn)

        fav_btn = QPushButton("☆")
        fav_btn.setFixedSize(28, 28)
        fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        fav_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                font-size: 16px;
                color: {theme['warning']};
                border-radius: 14px;
            }}
            QPushButton:hover {{
                background: {theme['warning_light']};
            }}
        """
        )
        fav_btn.setToolTip("즐겨찾기에 추가")
        fav_btn.clicked.connect(lambda: self.favoriteClicked.emit(self.numbers))
        layout.addWidget(fav_btn)

        self.setLayout(layout)
        self._apply_theme()

    def _copy_numbers(self):
        nums_str = " ".join(f"{number:02d}" for number in self.numbers)
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(nums_str)
        self.copyClicked.emit(self.numbers)

    def _apply_theme(self):
        theme = ThemeManager.get_theme()
        is_odd_row = self.index % 2 == 1
        bg_color = theme["bg_secondary"] if is_odd_row else theme["result_row_alt"]

        self.setStyleSheet(
            f"""
            QWidget {{
                background-color: {bg_color};
                border-bottom: 1px solid {theme['border_light']};
            }}
            QWidget:hover {{
                background-color: {theme['bg_hover']};
            }}
        """
        )
