from typing import Any, Dict, List

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from klotto.core.lotto_rules import normalize_bonus, normalize_numbers, normalize_positive_int
from klotto.core.stats import WinningStatsManager
from klotto.data.exporter import DataExporter
from klotto.data.favorites import FavoritesManager
from klotto.data.history import HistoryManager
from klotto.ui.theme import ThemeManager


class ExportImportDialog(QDialog):
    """데이터 내보내기/가져오기 다이얼로그"""

    def __init__(
        self,
        favorites_manager: FavoritesManager,
        history_manager: HistoryManager,
        stats_manager: WinningStatsManager,
        parent=None,
    ):
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

        theme = ThemeManager.get_theme()

        export_group = QGroupBox("📤 내보내기")
        export_layout = QVBoxLayout(export_group)

        data_layout = QHBoxLayout()
        data_layout.addWidget(QLabel("데이터 선택:"))
        self.data_combo = QComboBox()
        self.data_combo.addItems(["즐겨찾기", "히스토리", "당첨 통계"])
        data_layout.addWidget(self.data_combo)
        data_layout.addStretch()
        export_layout.addLayout(data_layout)

        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("형식:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["CSV", "JSON"])
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        export_layout.addLayout(format_layout)

        export_btn = QPushButton("💾 내보내기")
        export_btn.clicked.connect(self._export_data)
        export_layout.addWidget(export_btn)

        layout.addWidget(export_group)

        import_group = QGroupBox("📥 가져오기")
        import_layout = QVBoxLayout(import_group)

        import_desc = QLabel("JSON 파일에서 데이터를 가져옵니다.\n기존 데이터에 병합됩니다.")
        import_desc.setStyleSheet(f"color: {theme['text_muted']}; font-size: 12px;")
        import_layout.addWidget(import_desc)

        import_target_layout = QHBoxLayout()
        import_target_layout.addWidget(QLabel("가져오기 대상:"))
        self.import_combo = QComboBox()
        self.import_combo.addItems(["즐겨찾기", "히스토리", "당첨 통계"])
        import_target_layout.addWidget(self.import_combo)
        import_target_layout.addStretch()
        import_layout.addLayout(import_target_layout)

        import_btn = QPushButton("📂 파일 선택 및 가져오기")
        import_btn.clicked.connect(self._import_data)
        import_layout.addWidget(import_btn)

        layout.addWidget(import_group)
        layout.addStretch()

        close_btn = QPushButton("닫기")
        close_btn.setMinimumHeight(40)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    def _export_data(self):
        data_type_idx = self.data_combo.currentIndex()
        format_idx = self.format_combo.currentIndex()

        if data_type_idx == 0:
            data = self.favorites_manager.get_all()
            data_type = "favorites"
            default_name = "lotto_favorites"
        elif data_type_idx == 1:
            data = self.history_manager.get_all()
            data_type = "history"
            default_name = "lotto_history"
        else:
            data = self.stats_manager.winning_data
            data_type = "winning_stats"
            default_name = "lotto_winning_stats"

        if not data:
            QMessageBox.warning(self, "데이터 없음", "내보낼 데이터가 없습니다.")
            return

        if format_idx == 0:
            ext = "csv"
            filter_str = "CSV 파일 (*.csv)"
        else:
            ext = "json"
            filter_str = "JSON 파일 (*.json)"

        filepath, _ = QFileDialog.getSaveFileName(self, "내보내기", f"{default_name}.{ext}", filter_str)
        if not filepath:
            return

        if format_idx == 0:
            success = DataExporter.export_to_csv(data, filepath, data_type)
        else:
            success = DataExporter.export_to_json(data, filepath)

        if success:
            QMessageBox.information(self, "완료", f"{len(data)}개 항목이 저장되었습니다.\n{filepath}")
        else:
            QMessageBox.warning(self, "오류", "내보내기에 실패했습니다.")

    def _import_data(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "가져오기", "", "JSON 파일 (*.json)")
        if not filepath:
            return

        data = DataExporter.import_from_json(filepath)
        if data is None:
            QMessageBox.warning(self, "오류", "파일을 읽는데 실패했습니다.")
            return
        if not isinstance(data, list):
            QMessageBox.warning(self, "오류", "올바른 JSON 배열 형식이 아닙니다.")
            return

        target_idx = self.import_combo.currentIndex()
        imported_count = 0

        if target_idx == 0:
            items_to_add: List[Dict[str, Any]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                numbers = normalize_numbers(item.get("numbers"))
                if not numbers:
                    continue
                memo = item.get("memo", "")
                if not isinstance(memo, str):
                    memo = str(memo)
                items_to_add.append({"numbers": numbers, "memo": memo})
            imported_count = self.favorites_manager.add_many(items_to_add)
        elif target_idx == 1:
            history_sets: List[List[int]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                numbers = normalize_numbers(item.get("numbers"))
                if not numbers:
                    continue
                history_sets.append(numbers)
            imported_count = len(self.history_manager.add_many(history_sets))
        else:
            existing_draws = {entry.get("draw_no") for entry in self.stats_manager.winning_data if isinstance(entry, dict)}
            for item in data:
                if not isinstance(item, dict):
                    continue
                draw_no = normalize_positive_int(item.get("draw_no"))
                numbers = normalize_numbers(item.get("numbers"))
                bonus = normalize_bonus(item.get("bonus"), numbers) if numbers else None
                draw_date = item.get("date")
                draw_date_value = draw_date if isinstance(draw_date, str) else None

                if draw_no is None or numbers is None or bonus is None or draw_no in existing_draws:
                    continue

                saved = self.stats_manager.add_winning_data(draw_no, numbers, bonus, draw_date=draw_date_value)
                if saved:
                    existing_draws.add(draw_no)
                    imported_count += 1

        QMessageBox.information(self, "완료", f"{imported_count}개 항목이 가져와졌습니다.\n(중복 항목은 제외됨)")

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
        """
        )
