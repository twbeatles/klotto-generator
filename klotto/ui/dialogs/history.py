from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout

from klotto.ui.dialogs.saved_numbers_base import SavedNumbersBaseDialog
from klotto.ui.theme import ThemeManager


class HistoryDialog(SavedNumbersBaseDialog):
    """생성 히스토리 다이얼로그"""

    def __init__(self, history_manager, parent=None):
        super().__init__(parent)
        self.history_manager = history_manager
        self.setWindowTitle("📜 생성 히스토리")
        self.setMinimumSize(550, 500)
        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        theme = ThemeManager.get_theme()

        header_layout = QHBoxLayout()
        header_label = QLabel("최근 생성된 번호 조합")
        header_label.setStyleSheet(
            f"""
            font-size: 18px;
            font-weight: bold;
            color: {theme['text_primary']};
        """
        )
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {theme['text_muted']}; font-size: 13px;")
        header_layout.addWidget(self.count_label)
        layout.addLayout(header_layout)

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
            QPushButton:hover {{ background-color: {theme['accent_hover']}; }}
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

        clear_btn = QPushButton("🗑️ 전체 삭제")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {theme['danger']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #C0392B; }}
        """
        )
        clear_btn.clicked.connect(self._clear_history)
        btn_layout.addWidget(clear_btn)

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
        history = self.history_manager.get_recent(100)
        for entry in history:
            numbers_str = " - ".join(f"{number:02d}" for number in entry["numbers"])
            created = entry.get("created_at", "")[:16].replace("T", " ")
            item = QListWidgetItem(f"🎱  {numbers_str}   [{created}]")
            item.setData(Qt.ItemDataRole.UserRole, entry["numbers"])
            self.list_widget.addItem(item)
        self.count_label.setText(f"총 {len(self.history_manager.get_all())}개")

    def _copy_selected(self):
        self._copy_selected_numbers("번호가 복사되었습니다:\n{numbers}")

    def _clear_history(self):
        if not self.history_manager.get_all():
            QMessageBox.information(self, "알림", "삭제할 히스토리가 없습니다.")
            return

        reply = QMessageBox.question(
            self,
            "히스토리 삭제",
            "모든 히스토리를 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.history_manager.clear()
            self._refresh_list()
            QMessageBox.information(self, "완료", "히스토리가 삭제되었습니다.")
