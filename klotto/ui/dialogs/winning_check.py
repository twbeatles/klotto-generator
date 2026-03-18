from typing import Any, Dict, List, Optional, Set, Tuple

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from klotto.core.draws import normalize_legacy_draw_payload
from klotto.core.lotto_rules import calculate_rank, normalize_numbers
from klotto.core.stats import WinningStatsManager
from klotto.data.favorites import FavoritesManager
from klotto.data.history import HistoryManager
from klotto.net.client import LottoNetworkManager
from klotto.ui.theme import ThemeManager
from klotto.ui.widgets import LottoBall


class WinningCheckDialog(QDialog):
    """당첨 확인 자동화 다이얼로그"""

    def __init__(
        self,
        favorites_manager: FavoritesManager,
        history_manager: HistoryManager,
        stats_manager: WinningStatsManager,
        parent=None,
        qr_payload: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(parent)
        self.favorites_manager = favorites_manager
        self.history_manager = history_manager
        self.stats_manager = stats_manager
        self.qr_payload = qr_payload
        self._pending_qr_payload: Optional[Dict[str, Any]] = None
        self._qr_network_manager: Optional[LottoNetworkManager] = None
        self._source_items: List[Dict[str, Any]] = []

        self.setWindowTitle("🎯 당첨 확인")
        self.setMinimumSize(650, 500)
        self._setup_ui()
        self._apply_theme()

        self._update_number_list()
        if self.qr_payload:
            self.source_group.setEnabled(False)
            self.source_combo.setEnabled(False)
            self.number_list.setEnabled(False)
            self.check_btn.setEnabled(False)
            QTimer.singleShot(0, self._run_qr_payload_check)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        theme = ThemeManager.get_theme()
        desc_text = "저장된 번호가 과거 당첨 번호와 일치하는지 확인합니다."
        if self.qr_payload:
            desc_text = "QR 스캔 번호를 해당 회차 당첨 번호와 즉시 비교합니다."
        desc_label = QLabel(desc_text)
        desc_label.setStyleSheet(f"color: {theme['text_secondary']}; font-size: 14px;")
        layout.addWidget(desc_label)

        self.source_group = QGroupBox("확인할 번호 선택")
        source_layout = QVBoxLayout(self.source_group)

        self.source_combo = QComboBox()
        self.source_combo.addItem("즐겨찾기에서 선택")
        self.source_combo.addItem("히스토리에서 선택")
        self.source_combo.currentIndexChanged.connect(self._update_number_list)
        source_layout.addWidget(self.source_combo)

        self.number_list = QListWidget()
        self.number_list.setMaximumHeight(150)
        source_layout.addWidget(self.number_list)
        layout.addWidget(self.source_group)

        self.check_btn = QPushButton("🔍 당첨 확인 실행")
        self.check_btn.setMinimumHeight(45)
        self.check_btn.clicked.connect(self._run_check)
        layout.addWidget(self.check_btn)

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

        close_btn = QPushButton("닫기")
        close_btn.setMinimumHeight(40)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    def _update_number_list(self):
        self.number_list.clear()
        self._source_items = []

        if self.source_combo.currentIndex() == 0:
            for fav in self.favorites_manager.get_all():
                nums = fav.get("numbers", [])
                memo = fav.get("memo", "")
                text = f"{', '.join(map(str, nums))}"
                if memo:
                    text += f" ({memo})"
                self.number_list.addItem(text)
                self._source_items.append({"numbers": nums, "source": "favorites"})
        else:
            for hist in self.history_manager.get_all():
                nums = hist.get("numbers", [])
                self.number_list.addItem(f"{', '.join(map(str, nums))}")
                self._source_items.append({"numbers": nums, "source": "history"})

    def _clear_results(self):
        while self.result_inner_layout.count():
            item = self.result_inner_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_info_result(self, text: str, color: Optional[str] = None):
        theme = ThemeManager.get_theme()
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {color or theme['text_muted']}; padding: 20px;")
        self.result_inner_layout.addWidget(label)

    def _build_result_row(
        self,
        header_text: str,
        my_numbers: Set[int],
        winning_numbers: Set[int],
        bonus: int,
    ) -> Tuple[QFrame, int, bool, Optional[int]]:
        theme = ThemeManager.get_theme()
        matched = my_numbers & winning_numbers
        match_count = len(matched)
        bonus_matched = bonus in my_numbers
        rank = calculate_rank(match_count, bonus_matched)

        result_row = QFrame()
        result_row.setStyleSheet(
            f"""
            QFrame {{
                background-color: {theme['bg_secondary']};
                border: 1px solid {theme['border']};
                border-radius: 8px;
                padding: 10px;
            }}
        """
        )
        row_layout = QVBoxLayout(result_row)

        header = QHBoxLayout()
        draw_label = QLabel(header_text)
        draw_label.setStyleSheet(f"font-weight: bold; color: {theme['accent']};")
        header.addWidget(draw_label)

        if rank:
            rank_label = QLabel(f"🎉 {rank}등")
            rank_colors = {1: "#FF0000", 2: "#FF6600", 3: "#FFCC00", 4: "#00CC00", 5: "#0066CC"}
            rank_label.setStyleSheet(f"font-weight: bold; color: {rank_colors.get(rank, theme['text_primary'])};")
        else:
            rank_label = QLabel("미당첨")
            rank_label.setStyleSheet(f"font-weight: bold; color: {theme['text_muted']};")
        header.addWidget(rank_label)

        match_text = f"일치: {match_count}개"
        if bonus_matched:
            match_text += " + 보너스"
        match_label = QLabel(match_text)
        match_label.setStyleSheet(f"color: {theme['text_secondary']};")
        header.addWidget(match_label)
        header.addStretch()
        row_layout.addLayout(header)

        my_nums_layout = QHBoxLayout()
        my_nums_layout.addWidget(QLabel("내 번호:"))
        for number in sorted(my_numbers):
            my_nums_layout.addWidget(LottoBall(number, size=30, highlighted=(number in matched)))
        my_nums_layout.addStretch()
        row_layout.addLayout(my_nums_layout)

        win_nums_layout = QHBoxLayout()
        win_nums_layout.addWidget(QLabel("당첨 번호:"))
        for number in sorted(winning_numbers):
            win_nums_layout.addWidget(LottoBall(number, size=30, highlighted=(number in matched)))
        win_nums_layout.addWidget(QLabel("+"))
        win_nums_layout.addWidget(LottoBall(bonus, size=30, highlighted=bonus_matched))
        win_nums_layout.addWidget(QLabel("보너스"))
        win_nums_layout.addStretch()
        row_layout.addLayout(win_nums_layout)

        return result_row, match_count, bonus_matched, rank

    def _run_check(self):
        if self.qr_payload:
            self._run_qr_payload_check()
            return

        self._clear_results()

        row = self.number_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "선택 필요", "확인할 번호를 선택하세요.")
            return

        if row >= len(self._source_items):
            return

        normalized = normalize_numbers(self._source_items[row].get("numbers", []))
        if not normalized:
            self._add_info_result("선택한 번호 데이터 형식이 올바르지 않습니다.", ThemeManager.get_theme()["danger"])
            return
        my_numbers = set(normalized)

        winning_data = self.stats_manager.winning_data
        if not winning_data:
            self._add_info_result("확인할 당첨 데이터가 없습니다.\n당첨 정보 위젯에서 회차를 조회해 주세요.")
            return

        found_any = False
        for win_data in winning_data:
            draw_no = int(win_data["draw_no"])
            winning_numbers = set(win_data["numbers"])
            bonus = int(win_data["bonus"])

            result_row, match_count, _, _ = self._build_result_row(
                f"#{draw_no}회",
                my_numbers,
                winning_numbers,
                bonus,
            )
            if match_count >= 3:
                found_any = True
                self.result_inner_layout.addWidget(result_row)

        if not found_any:
            self._add_info_result("😢 3개 이상 일치하는 회차가 없습니다.")

    def _normalize_qr_payload(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            draw_no = int(payload.get("draw_no", 0))
        except (TypeError, ValueError):
            return None
        if draw_no <= 0:
            return None

        sets = payload.get("sets")
        if not isinstance(sets, list):
            return None

        normalized_sets: List[List[int]] = []
        for entry in sets:
            normalized = normalize_numbers(entry)
            if normalized:
                normalized_sets.append(normalized)

        if not normalized_sets:
            return None

        return {"draw_no": draw_no, "sets": normalized_sets}

    def _run_qr_payload_check(self):
        self._clear_results()
        normalized_payload = self._normalize_qr_payload(self.qr_payload or {})
        if not normalized_payload:
            self._add_info_result("QR 데이터 형식이 올바르지 않습니다.", ThemeManager.get_theme()["danger"])
            self.check_btn.setEnabled(True)
            return

        draw_no = normalized_payload["draw_no"]
        draw_data = self.stats_manager.get_draw_data(draw_no)
        if draw_data:
            self._render_qr_results(normalized_payload, draw_data)
            self.check_btn.setEnabled(True)
            return

        self._pending_qr_payload = normalized_payload
        self._ensure_qr_network_manager()
        self._add_info_result(f"{draw_no}회차 데이터를 가져오는 중입니다...")
        self.check_btn.setEnabled(False)
        manager = self._qr_network_manager
        if manager is None:
            self._on_qr_draw_error("QR 네트워크 매니저를 초기화하지 못했습니다.")
            return
        manager.fetch_draw(draw_no)

    def _ensure_qr_network_manager(self):
        if self._qr_network_manager:
            return
        self._qr_network_manager = LottoNetworkManager(self)
        self._qr_network_manager.dataLoaded.connect(self._on_qr_draw_loaded)
        self._qr_network_manager.errorOccurred.connect(self._on_qr_draw_error)

    def _on_qr_draw_loaded(self, data: dict):
        if not self._pending_qr_payload:
            return

        normalized_draw = normalize_legacy_draw_payload(data)
        if not normalized_draw:
            self._on_qr_draw_error("QR 회차 데이터 형식이 올바르지 않습니다.")
            return

        expected_draw = self._pending_qr_payload["draw_no"]
        if normalized_draw["draw_no"] != expected_draw:
            self._on_qr_draw_error("요청한 회차와 다른 응답이 수신되었습니다.")
            return

        status = self.stats_manager.upsert_winning_data(
            normalized_draw["draw_no"],
            normalized_draw["numbers"],
            normalized_draw["bonus"],
            draw_date=normalized_draw["date"] or None,
            first_prize=normalized_draw.get("first_prize"),
            first_winners=normalized_draw.get("first_winners"),
            total_sales=normalized_draw.get("total_sales"),
        )
        if status == "invalid":
            self._on_qr_draw_error("QR 회차 데이터를 저장하지 못했습니다.")
            return
        draw_data = self.stats_manager.get_draw_data(expected_draw)
        if not draw_data:
            self._on_qr_draw_error("QR 회차 데이터를 저장했지만 조회에 실패했습니다.")
            return

        self._render_qr_results(self._pending_qr_payload, draw_data)
        self._pending_qr_payload = None
        self.check_btn.setEnabled(True)

    def _on_qr_draw_error(self, msg: str):
        self._clear_results()
        self._add_info_result(f"QR 회차 데이터를 가져오지 못했습니다.\n{msg}", ThemeManager.get_theme()["danger"])
        self._pending_qr_payload = None
        self.check_btn.setEnabled(True)

    def _render_qr_results(self, payload: Dict[str, Any], draw_data: Dict[str, Any]):
        self._clear_results()
        draw_no = int(draw_data.get("draw_no", payload["draw_no"]))
        draw_date = draw_data.get("date", "")
        if draw_date:
            self._add_info_result(f"기준 회차: {draw_no}회 ({draw_date})", ThemeManager.get_theme()["accent"])
        else:
            self._add_info_result(f"기준 회차: {draw_no}회", ThemeManager.get_theme()["accent"])

        winning_numbers = set(draw_data.get("numbers", []))
        bonus = int(draw_data.get("bonus", 0))
        if len(winning_numbers) != 6 or bonus < 1 or bonus > 45:
            self._add_info_result("저장된 당첨 데이터가 올바르지 않습니다.", ThemeManager.get_theme()["danger"])
            self.check_btn.setEnabled(True)
            return

        for index, numbers in enumerate(payload["sets"], start=1):
            result_row, _, _, _ = self._build_result_row(
                f"#{draw_no}회 | QR 게임 {index}",
                set(numbers),
                winning_numbers,
                bonus,
            )
            self.result_inner_layout.addWidget(result_row)

        self.check_btn.setEnabled(True)

    def closeEvent(self, a0: Optional[QCloseEvent]):
        if self._qr_network_manager:
            self._qr_network_manager.cancel()
        if a0 is not None:
            super().closeEvent(a0)

    def _apply_theme(self):
        theme = ThemeManager.get_theme()
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {theme['bg_primary']};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {theme['border']};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: {theme['bg_secondary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                padding: 0 8px;
            }}
            QPushButton {{
                background-color: {theme['accent']};
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                padding: 10px;
            }}
            QPushButton:hover {{
                background-color: {theme['accent_hover']};
            }}
            QComboBox {{
                padding: 8px;
                border: 1px solid {theme['border']};
                border-radius: 6px;
                background-color: {theme['bg_secondary']};
            }}
            QListWidget {{
                border: 1px solid {theme['border']};
                border-radius: 6px;
                background-color: {theme['bg_secondary']};
            }}
        """
        )
