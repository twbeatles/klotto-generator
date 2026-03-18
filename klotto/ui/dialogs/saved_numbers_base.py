from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QListWidget, QMessageBox, QDialog

from klotto.ui.theme import ThemeManager


class SavedNumbersBaseDialog(QDialog):
    """히스토리/즐겨찾기 다이얼로그의 공통 동작을 제공한다."""

    list_widget: QListWidget

    def _get_selected_numbers(self) -> Optional[List[int]]:
        row = self.list_widget.currentRow()
        if row < 0:
            return None

        item = self.list_widget.item(row)
        if item is None:
            return None

        raw_numbers = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(raw_numbers, list):
            return None

        try:
            return [int(number) for number in raw_numbers]
        except (TypeError, ValueError):
            return None

    def _copy_selected_numbers(self, success_message: str):
        numbers = self._get_selected_numbers()
        if not numbers:
            QMessageBox.warning(self, "선택 필요", "복사할 항목을 선택하세요.")
            return

        clipboard = QApplication.clipboard()
        if clipboard is None:
            QMessageBox.warning(self, "오류", "클립보드를 사용할 수 없습니다.")
            return

        nums_str = " ".join(f"{number:02d}" for number in numbers)
        clipboard.setText(nums_str)
        QMessageBox.information(self, "복사 완료", success_message.format(numbers=nums_str))

    def _show_selected_qr(self):
        numbers = self._get_selected_numbers()
        if not numbers:
            QMessageBox.warning(self, "선택 필요", "QR 코드를 볼 항목을 선택하세요.")
            return

        from .qr_code import QRCodeDialog

        dialog = QRCodeDialog(numbers, self)
        dialog.exec()

    def _apply_list_theme(self):
        theme = ThemeManager.get_theme()
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {theme['bg_primary']};
            }}
            QListWidget {{
                background-color: {theme['bg_secondary']};
                border: 1px solid {theme['border']};
                border-radius: 8px;
                padding: 5px;
            }}
            QListWidget::item {{
                padding: 12px;
                border-radius: 6px;
                font-size: 14px;
                color: {theme['text_primary']};
            }}
            QListWidget::item:alternate {{
                background-color: {theme['result_row_alt']};
            }}
            QListWidget::item:selected {{
                background-color: {theme['accent_light']};
                color: {theme['accent']};
            }}
            QListWidget::item:hover {{
                background-color: {theme['bg_hover']};
            }}
        """
        )
