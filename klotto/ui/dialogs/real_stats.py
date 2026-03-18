from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from klotto.core.draws import estimate_latest_draw, normalize_legacy_draw_payload
from klotto.logging import logger
from klotto.net.client import LottoNetworkManager
from klotto.ui.theme import ThemeManager
from klotto.ui.widgets import LottoBall


class RealStatsDialog(QDialog):
    """실제 당첨 번호 통계 다이얼로그"""

    def __init__(self, stats_manager, parent=None):
        super().__init__(parent)
        self.stats_manager = stats_manager
        self.network_manager = LottoNetworkManager(self)
        self.network_manager.dataLoaded.connect(self._on_data_received)
        self.network_manager.errorOccurred.connect(self._on_error)
        self._pending_sync_count = 0

        self.setWindowTitle("📈 실제 당첨 번호 통계")
        self.setMinimumSize(600, 550)
        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        theme = ThemeManager.get_theme()

        header_layout = QHBoxLayout()
        header_label = QLabel("📊 당첨 번호 통계")
        header_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {theme['text_primary']};")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        self.sync_btn = QPushButton("🔄 최근 5회 동기화")
        self.sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sync_btn.clicked.connect(self._sync_recent_data)
        self.sync_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {theme['accent']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {theme['accent_hover']}; }}
        """
        )
        header_layout.addWidget(self.sync_btn)
        layout.addLayout(header_layout)

        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(f"color: {theme['accent']}; font-weight: bold;")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)

        analysis = self.stats_manager.get_frequency_analysis()
        range_dist = self.stats_manager.get_range_distribution()
        recent = self.stats_manager.get_recent_trend(5)

        if not analysis:
            no_data_label = QLabel(
                "📊 아직 수집된 당첨 데이터가 없습니다.\n\n"
                "당첨 정보 위젯에서 회차를 조회하면\n"
                "자동으로 통계가 수집됩니다."
            )
            no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_data_label.setStyleSheet(f"color: {theme['text_muted']}; font-size: 15px;")
            layout.addWidget(no_data_label)

            close_btn = QPushButton("닫기")
            close_btn.clicked.connect(self.close)
            layout.addWidget(close_btn)
            return

        summary_label = QLabel(f"📊 총 {analysis['total_draws']}회차 분석 결과")
        summary_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {theme['accent']};")
        layout.addWidget(summary_label)

        hot_group = QGroupBox("🔥 핫 넘버 TOP 10 (가장 많이 나온 번호)")
        hot_layout = QHBoxLayout(hot_group)
        hot_layout.setSpacing(8)
        for num, count in analysis["hot_numbers"]:
            hot_layout.addWidget(LottoBall(num, size=36))
            count_label = QLabel(f"({count})")
            count_label.setStyleSheet(f"color: {theme['text_muted']}; font-size: 11px;")
            hot_layout.addWidget(count_label)
        hot_layout.addStretch()
        layout.addWidget(hot_group)

        cold_group = QGroupBox("❄️ 콜드 넘버 (가장 적게 나온 번호)")
        cold_layout = QHBoxLayout(cold_group)
        cold_layout.setSpacing(8)
        for num, count in analysis["cold_numbers"]:
            cold_layout.addWidget(LottoBall(num, size=36))
            count_label = QLabel(f"({count})")
            count_label.setStyleSheet(f"color: {theme['text_muted']}; font-size: 11px;")
            cold_layout.addWidget(count_label)
        cold_layout.addStretch()
        layout.addWidget(cold_group)

        if range_dist:
            range_group = QGroupBox("📊 번호대별 분포")
            range_layout = QVBoxLayout(range_group)
            total_nums = sum(range_dist.values())
            for range_name, count in range_dist.items():
                pct = (count / total_nums * 100) if total_nums > 0 else 0
                row_layout = QHBoxLayout()

                range_label = QLabel(f"{range_name}:")
                range_label.setFixedWidth(60)
                range_label.setStyleSheet(f"font-weight: bold; color: {theme['text_primary']};")

                bar = QLabel("█" * int(pct * 2))
                bar.setStyleSheet(f"color: {theme['accent']};")

                pct_label = QLabel(f"{count}회 ({pct:.1f}%)")
                pct_label.setStyleSheet(f"color: {theme['text_secondary']};")

                row_layout.addWidget(range_label)
                row_layout.addWidget(bar)
                row_layout.addWidget(pct_label)
                row_layout.addStretch()
                range_layout.addLayout(row_layout)

            layout.addWidget(range_group)

        if recent:
            recent_group = QGroupBox("📅 최근 당첨 번호")
            recent_layout = QVBoxLayout(recent_group)
            for data in recent[:5]:
                row = QHBoxLayout()
                draw_label = QLabel(f"#{data['draw_no']}회")
                draw_label.setFixedWidth(70)
                draw_label.setStyleSheet(f"font-weight: bold; color: {theme['accent']};")
                row.addWidget(draw_label)

                for number in data["numbers"]:
                    row.addWidget(LottoBall(number, size=30))

                plus_label = QLabel("+")
                plus_label.setStyleSheet(f"color: {theme['text_muted']};")
                row.addWidget(plus_label)
                row.addWidget(LottoBall(data["bonus"], size=30, highlighted=True))
                row.addStretch()
                recent_layout.addLayout(row)
            layout.addWidget(recent_group)

        layout.addStretch()

        close_btn = QPushButton("닫기")
        close_btn.setMinimumHeight(40)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

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
        """
        )

    def _sync_recent_data(self):
        estimated_draw = estimate_latest_draw()
        draws = list(range(max(1, estimated_draw - 4), estimated_draw + 1))
        if not draws:
            return

        self.sync_btn.setEnabled(False)
        self.progress_label.setText("데이터 동기화 중...")
        self.progress_label.setVisible(True)
        self._pending_sync_count = len(draws)
        self.network_manager.fetch_draws(draws)

    def _complete_sync_step(self):
        if self._pending_sync_count > 0:
            self._pending_sync_count -= 1

        if self._pending_sync_count <= 0:
            self.sync_btn.setEnabled(True)
            if not self.progress_label.text().startswith("오류:"):
                self.progress_label.setText("동기화 완료")

    def _on_data_received(self, data):
        try:
            normalized = normalize_legacy_draw_payload(data)
            if not normalized:
                return

            saved = self.stats_manager.add_winning_data(
                normalized["draw_no"],
                normalized["numbers"],
                normalized["bonus"],
                draw_date=normalized["date"] or None,
            )
            if saved:
                self.progress_label.setText(f"{normalized['draw_no']}회차 저장 완료")
            else:
                self.progress_label.setText(f"{normalized['draw_no']}회차는 이미 존재하거나 저장에 실패했습니다.")
        except Exception as exc:
            logger.error("Sync error: %s", exc)
        finally:
            self._complete_sync_step()

    def _on_error(self, msg: str):
        self.progress_label.setText(f"오류: {msg}")
        self._complete_sync_step()
