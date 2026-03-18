from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout

from klotto.data.favorites import FavoritesManager
from klotto.ui.dialogs.saved_numbers_base import SavedNumbersBaseDialog
from klotto.ui.theme import ThemeManager


class FavoritesDialog(SavedNumbersBaseDialog):
    """즐겨찾기 목록 다이얼로그 - 개선된 UX"""

    def __init__(self, favorites_manager: FavoritesManager, parent=None):
        super().__init__(parent)
        self.favorites_manager = favorites_manager
        self.setWindowTitle("⭐ 즐겨찾기")
        self.setMinimumSize(500, 400)
        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        theme = ThemeManager.get_theme()

        header_label = QLabel("저장된 번호 조합")
        header_label.setStyleSheet(
            f"""
            font-size: 18px;
            font-weight: bold;
            color: {theme['text_primary']};
            padding-bottom: 5px;
        """
        )
        layout.addWidget(header_label)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {theme['text_muted']}; font-size: 13px;")
        layout.addWidget(self.count_label)

        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self._refresh_list()
        layout.addWidget(self.list_widget, 1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        copy_btn = QPushButton("📋 복사")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {theme['accent']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {theme['accent_hover']};
            }}
        """
        )
        copy_btn.clicked.connect(self._copy_selected)
        btn_layout.addWidget(copy_btn)

        qr_btn = QPushButton("📱 QR")
        qr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        qr_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {theme['success']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {theme['success_light']}; color: {theme['success']}; }}
        """
        )
        qr_btn.clicked.connect(self._show_selected_qr)
        btn_layout.addWidget(qr_btn)

        delete_btn = QPushButton("🗑️ 삭제")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {theme['danger']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #C0392B;
            }}
        """
        )
        delete_btn.clicked.connect(self._delete_selected)
        btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("닫기")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {theme['neutral']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {theme['bg_tertiary']};
                color: {theme['text_primary']};
            }}
        """
        )
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _apply_theme(self):
        self._apply_list_theme()

    def _refresh_list(self):
        self.list_widget.clear()
        favorites = self.favorites_manager.get_all()
        for favorite in favorites:
            numbers_str = " - ".join(f"{number:02d}" for number in favorite["numbers"])
            created = favorite.get("created_at", "")[:10]
            memo = favorite.get("memo", "")

            display_text = f"🎱  {numbers_str}"
            if memo:
                display_text += f"  ({memo})"
            display_text += f"  [{created}]"

            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, favorite["numbers"])
            self.list_widget.addItem(item)

        self.count_label.setText(f"총 {len(favorites)}개의 즐겨찾기")

    def _copy_selected(self):
        self._copy_selected_numbers("번호가 클립보드에 복사되었습니다:\n{numbers}")

    def _delete_selected(self):
        row = self.list_widget.currentRow()
        if row < 0:
            QMessageBox.warning(self, "선택 필요", "삭제할 항목을 선택하세요.")
            return

        reply = QMessageBox.question(
            self,
            "삭제 확인",
            "선택한 즐겨찾기를 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.favorites_manager.remove(row)
            self._refresh_list()
