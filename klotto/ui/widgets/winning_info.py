from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from klotto.core.draws import estimate_latest_draw, normalize_legacy_draw_payload
from klotto.core.stats import WinningStatsManager
from klotto.logging import logger
from klotto.net.client import LottoNetworkManager
from klotto.ui.theme import ThemeManager
from klotto.ui.widgets.lotto_ball import LottoBall


class WinningInfoWidget(QWidget):
    """지난 회차 당첨 정보를 표시하는 위젯"""

    dataLoaded = pyqtSignal(dict)

    def __init__(self, stats_manager: WinningStatsManager, parent=None):
        super().__init__(parent)
        self.stats_manager = stats_manager
        self.network_manager = LottoNetworkManager(self)
        self.network_manager.dataLoaded.connect(self._on_data_received)
        self.network_manager.errorOccurred.connect(self._on_error)

        self.current_draw_no = estimate_latest_draw()
        self.current_data: Optional[Dict[str, Any]] = None
        self._pending_draw_no: Optional[int] = None
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

        self.title_label = QLabel("지난 회차 당첨 정보")
        self.title_label.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {ThemeManager.get_theme()['text_primary']};"
        )
        header_layout.addWidget(self.title_label)

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
        self.title_label.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {theme['text_primary']};"
        )
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
        self._set_status(self.status_label.text() or "로딩 중...", "muted")

    def _toggle_collapse(self):
        self._is_collapsed = not self._is_collapsed
        self.content_widget.setVisible(not self._is_collapsed)
        self.toggle_btn.setText("▶" if self._is_collapsed else "▼")

    def _on_refresh_clicked(self):
        self.load_winning_info(self.draw_spinbox.value())

    def _set_status(self, text: str, tone: str = "muted"):
        theme = ThemeManager.get_theme()
        color_map = {
            "muted": theme["text_muted"],
            "accent": theme["accent"],
            "danger": theme["danger"],
        }
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color_map.get(tone, theme['text_muted'])}; font-size: 14px;")
        self.status_label.setVisible(True)

    def _clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

    def _render_draw_data(self, draw_data: Dict[str, Any]):
        self.current_data = dict(draw_data)
        self._clear_layout(self.numbers_layout)
        self._clear_layout(self.prize_layout)

        theme = ThemeManager.get_theme()
        draw_no = int(draw_data["draw_no"])
        draw_date = str(draw_data.get("date", ""))
        numbers = list(draw_data["numbers"])
        bonus = int(draw_data["bonus"])

        date_label = QLabel(f"<b>{draw_no}회</b> ({draw_date})" if draw_date else f"<b>{draw_no}회</b>")
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

        first_prize = int(draw_data.get("first_prize", 0))
        first_winners = int(draw_data.get("first_winners", 0))
        total_sales = int(draw_data.get("total_sales", 0))

        if first_prize > 0 and first_winners > 0:
            prize_text = f"🏆 <b style='color:{theme['danger']};'>1등</b> <b>{first_prize:,}원</b> ({first_winners}명)"
        else:
            prize_text = "🏆 1등 정보: <b>정보 없음</b>"
        prize_info = QLabel(prize_text)
        prize_info.setStyleSheet("font-size: 14px;")
        self.prize_layout.addWidget(prize_info)

        if total_sales > 0:
            sales_text = f"📊 판매액: <b>{total_sales:,}원</b>"
        else:
            sales_text = "📊 판매액: <b>정보 없음</b>"
        sales_info = QLabel(sales_text)
        sales_info.setStyleSheet(f"font-size: 13px; color: {theme['text_secondary']};")
        self.prize_layout.addWidget(sales_info)

        self.prize_widget.setVisible(True)

    def _reset_view(self):
        self.current_data = None
        self._clear_layout(self.numbers_layout)
        self._clear_layout(self.prize_layout)
        self.numbers_widget.setVisible(False)
        self.prize_widget.setVisible(False)

    def load_winning_info(self, draw_no: int):
        self._pending_draw_no = draw_no
        self.refresh_btn.setEnabled(False)

        cached = self.stats_manager.get_draw_data(draw_no)
        if cached:
            self._render_draw_data(cached)
            self._set_status("DB 캐시 표시 중 · 최신 정보 확인 중", "accent")
        else:
            self._reset_view()
            self._set_status("최신 정보 확인 중", "accent")

        self.network_manager.fetch_draw(draw_no)

    def _on_data_received(self, data: dict):
        normalized = normalize_legacy_draw_payload(data)
        if not normalized:
            logger.error("Invalid winning info payload: %s", data)
            self._on_error("당첨 데이터 형식 오류")
            return

        expected_draw_no = self._pending_draw_no
        if expected_draw_no and normalized["draw_no"] != expected_draw_no:
            logger.warning("Ignoring stale winning info payload for draw #%s", normalized["draw_no"])
            return

        status = self.stats_manager.upsert_winning_data(
            normalized["draw_no"],
            normalized["numbers"],
            normalized["bonus"],
            draw_date=normalized.get("date"),
            first_prize=normalized.get("first_prize"),
            first_winners=normalized.get("first_winners"),
            total_sales=normalized.get("total_sales"),
        )
        if status == "invalid":
            self._on_error("당첨 데이터 저장 오류")
            return

        draw_data = self.stats_manager.get_draw_data(normalized["draw_no"]) or normalized
        self._render_draw_data(draw_data)
        self.refresh_btn.setEnabled(True)
        self._set_status("최신 정보 반영 완료", "accent")
        self.dataLoaded.emit(dict(draw_data))

    def _on_error(self, error_msg: str):
        self.refresh_btn.setEnabled(True)

        if self.current_data is not None:
            self._set_status(f"네트워크 오류 · DB 캐시 표시 유지 중 ({error_msg})", "danger")
            return

        self._reset_view()
        self._set_status(f"네트워크 오류: {error_msg}", "danger")

    def get_winning_numbers(self) -> Tuple[List[int], int]:
        if not self.current_data:
            return [], 0
        return list(self.current_data["numbers"]), int(self.current_data["bonus"])
