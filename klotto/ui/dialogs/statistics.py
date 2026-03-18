from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from klotto.ui.theme import ThemeManager
from klotto.ui.widgets import LottoBall


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

        theme = ThemeManager.get_theme()
        stats = self.history_manager.get_statistics()

        header_label = QLabel("생성 번호 통계")
        header_label.setStyleSheet(
            f"""
            font-size: 18px;
            font-weight: bold;
            color: {theme['text_primary']};
        """
        )
        layout.addWidget(header_label)

        if not stats:
            no_data = QLabel("아직 생성된 번호가 없습니다.\n번호를 생성하면 통계가 표시됩니다.")
            no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_data.setStyleSheet(f"color: {theme['text_muted']}; font-size: 14px; padding: 40px;")
            layout.addWidget(no_data)
        else:
            total_label = QLabel(f"총 {stats['total_sets']}개 조합 생성됨")
            total_label.setStyleSheet(f"color: {theme['text_secondary']}; font-size: 14px;")
            layout.addWidget(total_label)

            most_group = QGroupBox("🔥 가장 많이 선택된 번호")
            most_layout = QHBoxLayout(most_group)
            most_layout.setSpacing(5)
            for num, count in stats["most_common"][:7]:
                most_layout.addWidget(LottoBall(num, size=32))
                count_label = QLabel(f"({count})")
                count_label.setStyleSheet(f"color: {theme['text_muted']}; font-size: 11px;")
                most_layout.addWidget(count_label)
            most_layout.addStretch()
            layout.addWidget(most_group)

            least_group = QGroupBox("❄️ 가장 적게 선택된 번호")
            least_layout = QHBoxLayout(least_group)
            least_layout.setSpacing(5)
            for num, count in stats["least_common"][:7]:
                least_layout.addWidget(LottoBall(num, size=32))
                count_label = QLabel(f"({count})")
                count_label.setStyleSheet(f"color: {theme['text_muted']}; font-size: 11px;")
                least_layout.addWidget(count_label)
            least_layout.addStretch()
            layout.addWidget(least_group)

            range_group = QGroupBox("📈 번호대별 분포")
            range_layout = QGridLayout(range_group)

            range_counts = {label: 0 for label in ["1-10", "11-20", "21-30", "31-40", "41-45"]}
            for entry in self.history_manager.get_all():
                for num in entry["numbers"]:
                    if num <= 10:
                        range_counts["1-10"] += 1
                    elif num <= 20:
                        range_counts["11-20"] += 1
                    elif num <= 30:
                        range_counts["21-30"] += 1
                    elif num <= 40:
                        range_counts["31-40"] += 1
                    else:
                        range_counts["41-45"] += 1

            total_nums = sum(range_counts.values()) or 1
            for col, (range_name, count) in enumerate(range_counts.items()):
                pct = count / total_nums * 100
                label = QLabel(f"{range_name}: {count} ({pct:.1f}%)")
                label.setStyleSheet(f"font-size: 13px; color: {theme['text_secondary']};")
                range_layout.addWidget(label, 0, col)

            layout.addWidget(range_group)

        layout.addStretch()

        close_btn = QPushButton("닫기")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {theme['neutral']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 24px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {theme['bg_tertiary']};
                color: {theme['text_primary']};
            }}
        """
        )
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setLayout(layout)

    def _apply_theme(self):
        theme = ThemeManager.get_theme()
        self.setStyleSheet(
            f"""
            QDialog {{ background-color: {theme['bg_primary']}; }}
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
        """
        )
