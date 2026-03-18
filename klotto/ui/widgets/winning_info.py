from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from klotto.core.draws import estimate_latest_draw, normalize_legacy_draw_payload
from klotto.logging import logger
from klotto.net.client import LottoNetworkManager
from klotto.ui.theme import ThemeManager
from klotto.ui.widgets.lotto_ball import LottoBall


class WinningInfoWidget(QWidget):
    """지난 회차 당첨 정보를 표시하는 위젯"""

    dataLoaded = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.network_manager = LottoNetworkManager(self)
        self.network_manager.dataLoaded.connect(self._on_data_received)
        self.network_manager.errorOccurred.connect(self._on_error)

        self.current_draw_no = estimate_latest_draw()
        self.current_data: Optional[Dict[str, Any]] = None
        self._is_collapsed = False
        self.initUI()
        self.load_winning_info(self.current_draw_no)

    def initUI(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        self.toggle_btn = QPushButton("▼")
        self.toggle_btn.setFixedSize(28, 28)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self._toggle_collapse)
        header_layout.addWidget(self.toggle_btn)

        title_label = QLabel("지난 회차 당첨 정보")
        title_label.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {ThemeManager.get_theme()['text_primary']};"
        )
        header_layout.addWidget(title_label)

        header_layout.addStretch()

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

        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

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
        theme = ThemeManager.get_theme()
        self.refresh_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {theme['accent']};
                color: white;
                border-radius: 5px;
                padding: 5px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {theme['accent_hover']}; }}
            QPushButton:disabled {{ background-color: {theme['bg_tertiary']}; color: {theme['text_muted']}; }}
        """
        )
        self.toggle_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {theme['text_secondary']};
                font-size: 12px;
            }}
            QPushButton:hover {{
                background: {theme['bg_tertiary']};
                border-radius: 4px;
            }}
        """
        )
        self.status_label.setStyleSheet(f"color: {theme['text_muted']}; font-size: 14px;")

    def _toggle_collapse(self):
        self._is_collapsed = not self._is_collapsed
        self.content_widget.setVisible(not self._is_collapsed)
        self.toggle_btn.setText("▶" if self._is_collapsed else "▼")

    def _on_refresh_clicked(self):
        self.load_winning_info(self.draw_spinbox.value())

    def load_winning_info(self, draw_no: int):
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("로딩 중...")
        self.status_label.setVisible(True)
        self.numbers_widget.setVisible(False)
        self.prize_widget.setVisible(False)
        self.network_manager.fetch_draw(draw_no)

    def _on_data_received(self, data: dict):
        normalized = normalize_legacy_draw_payload(data)
        if not normalized:
            logger.error("Invalid winning info payload: %s", data)
            self._on_error("당첨 데이터 형식 오류")
            return

        self.current_data = normalized
        self.refresh_btn.setEnabled(True)
        self.status_label.setVisible(False)
        self._clear_layout(self.numbers_layout)
        self._clear_layout(self.prize_layout)

        theme = ThemeManager.get_theme()
        draw_no = normalized["draw_no"]
        draw_date = normalized["date"]
        numbers = normalized["numbers"]
        bonus = normalized["bonus"]

        date_label = QLabel(f"<b>{draw_no}회</b> ({draw_date})")
        date_label.setStyleSheet(f"font-size: 13px; color: {theme['text_secondary']};")
        self.numbers_layout.addWidget(date_label)

        for number in numbers:
            self.numbers_layout.addWidget(LottoBall(number, size=34))

        plus_label = QLabel("+")
        plus_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {theme['text_muted']};")
        self.numbers_layout.addWidget(plus_label)

        self.numbers_layout.addWidget(LottoBall(bonus, size=34))

        bonus_label = QLabel("보너스")
        bonus_label.setStyleSheet(f"font-size: 11px; color: {theme['text_muted']};")
        self.numbers_layout.addWidget(bonus_label)
        self.numbers_widget.setVisible(True)

        first_prize = normalized["first_prize"]
        first_winners = normalized["first_winners"]
        total_sales = normalized["total_sales"]

        prize_info = QLabel(f"🏆 <b style='color:{theme['danger']};'>1등</b> <b>{first_prize:,}원</b> ({first_winners}명)")
        prize_info.setStyleSheet("font-size: 14px;")
        self.prize_layout.addWidget(prize_info)

        sales_info = QLabel(f"📊 판매액: <b>{total_sales:,}원</b>")
        sales_info.setStyleSheet(f"font-size: 13px; color: {theme['text_secondary']};")
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
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

    def get_winning_numbers(self) -> Tuple[List[int], int]:
        if not self.current_data:
            return [], 0
        return list(self.current_data["numbers"]), int(self.current_data["bonus"])
