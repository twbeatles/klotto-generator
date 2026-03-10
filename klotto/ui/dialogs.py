import datetime
from typing import Any, List, Dict, Optional, Set, Tuple
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QMessageBox, QGroupBox, QListWidget, QListWidgetItem,
    QGridLayout, QScrollArea, QWidget, QFrame, QComboBox, QFileDialog,
    QApplication
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QImage, QCloseEvent

from klotto.utils import logger, ThemeManager
from klotto.ui.widgets import LottoBall
from klotto.data.favorites import FavoritesManager
from klotto.data.history import HistoryManager
from klotto.core.stats import WinningStatsManager
from klotto.data.exporter import DataExporter

qrcode = None
try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

# ============================================================
# QR 코드 다이얼로그
# ============================================================
class QRCodeDialog(QDialog):
    """생성된 번호를 QR 코드로 표시"""
    
    def __init__(self, numbers: List[int], parent=None):
        super().__init__(parent)
        self.numbers = sorted(numbers)
        self.setWindowTitle("📱 QR 코드")
        self.setFixedSize(300, 350)
        self._setup_ui()
        self._apply_theme()
        
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        t = ThemeManager.get_theme()
        
        # 안내 텍스트
        nums_str = " ".join(f"{n:02d}" for n in self.numbers)
        info_label = QLabel(f"번호: {nums_str}")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {t['text_primary']};")
        layout.addWidget(info_label)
        
        # QR 코드 이미지
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setFixedSize(200, 200)
        self.qr_label.setStyleSheet("background-color: white; border-radius: 10px;")
        
        if HAS_QRCODE:
            self._generate_qr()
        else:
            self.qr_label.setText("qrcode 라이브러리가\n설치되지 않았습니다.")
            
        layout.addWidget(self.qr_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['accent']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['accent_hover']}; }}
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
    
    def _generate_qr(self):
        if not HAS_QRCODE or qrcode is None:
            self.qr_label.setText("qrcode 라이브러리가\n설치되지 않았습니다.")
            return

        try:
            # 텍스트 형식으로 생성 (단순 복사용)
            data = f"Lotto 6/45 Generator\nNumbers: {self.numbers}"
             
            qr = qrcode.QRCode(
                version=1,
                error_correction=1,
                box_size=10,
                border=2,
            )
            qr.add_data(data)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # PIL 이미지를 QPixmap으로 변환
            import io
            buffer = io.BytesIO()
            img.save(buffer, "PNG")
            qimg = QImage.fromData(buffer.getvalue())
            pixmap = QPixmap.fromImage(qimg)
            
            self.qr_label.setPixmap(pixmap.scaled(180, 180, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            
        except Exception as e:
            logger.error(f"QR Code generation failed: {e}")
            self.qr_label.setText("QR 생성 실패")

    def _apply_theme(self):
        t = ThemeManager.get_theme()
        self.setStyleSheet(f"background-color: {t['bg_primary']};")


# ============================================================
# 통계 다이얼로그
# ============================================================
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
        
        t = ThemeManager.get_theme()
        stats = self.history_manager.get_statistics()
        
        # 헤더
        header_label = QLabel("생성 번호 통계")
        header_label.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {t['text_primary']};
        """)
        layout.addWidget(header_label)
        
        if not stats:
            no_data = QLabel("아직 생성된 번호가 없습니다.\n번호를 생성하면 통계가 표시됩니다.")
            no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_data.setStyleSheet(f"color: {t['text_muted']}; font-size: 14px; padding: 40px;")
            layout.addWidget(no_data)
        else:
            # 총 생성 수
            total_label = QLabel(f"총 {stats['total_sets']}개 조합 생성됨")
            total_label.setStyleSheet(f"color: {t['text_secondary']}; font-size: 14px;")
            layout.addWidget(total_label)
            
            # 가장 많이 나온 번호
            most_group = QGroupBox("🔥 가장 많이 선택된 번호")
            most_layout = QHBoxLayout(most_group)
            most_layout.setSpacing(5)
            for num, count in stats['most_common'][:7]:
                ball = LottoBall(num, size=32)
                most_layout.addWidget(ball)
                count_lbl = QLabel(f"({count})")
                count_lbl.setStyleSheet(f"color: {t['text_muted']}; font-size: 11px;")
                most_layout.addWidget(count_lbl)
            most_layout.addStretch()
            layout.addWidget(most_group)
            
            # 가장 적게 나온 번호
            least_group = QGroupBox("❄️ 가장 적게 선택된 번호")
            least_layout = QHBoxLayout(least_group)
            least_layout.setSpacing(5)
            for num, count in stats['least_common'][:7]:
                ball = LottoBall(num, size=32)
                least_layout.addWidget(ball)
                count_lbl = QLabel(f"({count})")
                count_lbl.setStyleSheet(f"color: {t['text_muted']}; font-size: 11px;")
                least_layout.addWidget(count_lbl)
            least_layout.addStretch()
            layout.addWidget(least_group)
            
            # 번호대별 분포
            range_group = QGroupBox("📈 번호대별 분포")
            range_layout = QGridLayout(range_group)
            
            range_counts = {r: 0 for r in ['1-10', '11-20', '21-30', '31-40', '41-45']}
            for h in self.history_manager.get_all():
                for num in h['numbers']:
                    if num <= 10: range_counts['1-10'] += 1
                    elif num <= 20: range_counts['11-20'] += 1
                    elif num <= 30: range_counts['21-30'] += 1
                    elif num <= 40: range_counts['31-40'] += 1
                    else: range_counts['41-45'] += 1
            
            total_nums = sum(range_counts.values()) or 1
            col = 0
            for range_name, count in range_counts.items():
                pct = count / total_nums * 100
                lbl = QLabel(f"{range_name}: {count} ({pct:.1f}%)")
                lbl.setStyleSheet(f"font-size: 13px; color: {t['text_secondary']};")
                range_layout.addWidget(lbl, 0, col)
                col += 1
            
            layout.addWidget(range_group)
        
        layout.addStretch()
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['neutral']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 10px 24px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {t['bg_tertiary']};
                color: {t['text_primary']};
            }}
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.setLayout(layout)
    
    def _apply_theme(self):
        t = ThemeManager.get_theme()
        self.setStyleSheet(f"""
            QDialog {{ background-color: {t['bg_primary']}; }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {t['border']};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: {t['bg_secondary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                padding: 0 8px;
            }}
        """)


# ============================================================
# 히스토리 다이얼로그
# ============================================================
class HistoryDialog(QDialog):
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
        
        t = ThemeManager.get_theme()
        
        # 헤더
        header_layout = QHBoxLayout()
        header_label = QLabel("최근 생성된 번호 조합")
        header_label.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {t['text_primary']};
        """)
        header_layout.addWidget(header_label)
        
        header_layout.addStretch()
        
        # 히스토리 수
        count = len(self.history_manager.get_all())
        count_label = QLabel(f"총 {count}개")
        count_label.setStyleSheet(f"color: {t['text_muted']}; font-size: 13px;")
        header_layout.addWidget(count_label)
        
        layout.addLayout(header_layout)
        
        # 리스트 위젯
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self._refresh_list()
        layout.addWidget(self.list_widget, 1)
        
        # 버튼 영역
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        # 복사 버튼
        copy_btn = QPushButton("📋 복사")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['accent']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['accent_hover']}; }}
        """)
        copy_btn.clicked.connect(self._copy_selected)
        btn_layout.addWidget(copy_btn)
        
        # QR 버튼
        qr_btn = QPushButton("📱 QR")
        qr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        qr_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['success']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['success_light']}; color: {t['success']}; }}
        """)
        qr_btn.clicked.connect(self._show_selected_qr)
        btn_layout.addWidget(qr_btn)
        
        # 히스토리 삭제 버튼
        clear_btn = QPushButton("🗑️ 전체 삭제")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['danger']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #C0392B; }}
        """)
        clear_btn.clicked.connect(self._clear_history)
        btn_layout.addWidget(clear_btn)
        
        btn_layout.addStretch()
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['neutral']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {t['bg_tertiary']};
                color: {t['text_primary']};
            }}
        """)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def _apply_theme(self):
        t = ThemeManager.get_theme()
        self.setStyleSheet(f"""
            QDialog {{ background-color: {t['bg_primary']}; }}
            QListWidget {{
                background-color: {t['bg_secondary']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                padding: 5px;
            }}
            QListWidget::item {{
                padding: 10px 12px;
                border-radius: 6px;
                font-size: 14px;
            }}
            QListWidget::item:alternate {{ background-color: {t['result_row_alt']}; }}
            QListWidget::item:selected {{
                background-color: {t['accent_light']};
                color: {t['accent']};
            }}
            QListWidget::item:hover {{ background-color: {t['bg_hover']}; }}
        """)
    
    def _refresh_list(self):
        self.list_widget.clear()
        for h in self.history_manager.get_recent(100):
            numbers_str = " - ".join(f"{n:02d}" for n in h['numbers'])
            created = h.get('created_at', '')[:16].replace('T', ' ')
            
            item = QListWidgetItem(f"🎱  {numbers_str}   [{created}]")
            item.setData(Qt.ItemDataRole.UserRole, h['numbers'])
            self.list_widget.addItem(item)
    
    def _copy_selected(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            item = self.list_widget.item(row)
            if item is None:
                QMessageBox.warning(self, "선택 필요", "선택한 항목을 찾을 수 없습니다.")
                return
            raw_numbers = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(raw_numbers, list):
                QMessageBox.warning(self, "오류", "번호 데이터 형식이 올바르지 않습니다.")
                return
            numbers = [int(n) for n in raw_numbers]
            nums_str = " ".join(f"{n:02d}" for n in numbers)
            clipboard = QApplication.clipboard()
            if clipboard is None:
                QMessageBox.warning(self, "오류", "클립보드를 사용할 수 없습니다.")
                return
            clipboard.setText(nums_str)
            QMessageBox.information(self, "복사 완료", f"번호가 복사되었습니다:\n{nums_str}")
        else:
            QMessageBox.warning(self, "선택 필요", "복사할 항목을 선택하세요.")
            
    def _show_selected_qr(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            item = self.list_widget.item(row)
            if item is None:
                QMessageBox.warning(self, "선택 필요", "선택한 항목을 찾을 수 없습니다.")
                return
            raw_numbers = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(raw_numbers, list):
                QMessageBox.warning(self, "오류", "번호 데이터 형식이 올바르지 않습니다.")
                return
            numbers = [int(n) for n in raw_numbers]
            dialog = QRCodeDialog(numbers, self)
            dialog.exec()
        else:
            QMessageBox.warning(self, "선택 필요", "QR 코드를 볼 항목을 선택하세요.")
    
    def _clear_history(self):
        if not self.history_manager.get_all():
            QMessageBox.information(self, "알림", "삭제할 히스토리가 없습니다.")
            return
        
        reply = QMessageBox.question(
            self,
            "히스토리 삭제",
            "모든 히스토리를 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.history_manager.clear()
            self._refresh_list()
            QMessageBox.information(self, "완료", "히스토리가 삭제되었습니다.")


# ============================================================
# 즐겨찾기 다이얼로그
# ============================================================
class FavoritesDialog(QDialog):
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
        
        t = ThemeManager.get_theme()
        
        # 헤더
        header_label = QLabel("저장된 번호 조합")
        header_label.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {t['text_primary']};
            padding-bottom: 5px;
        """)
        layout.addWidget(header_label)
        
        # 즐겨찾기 수
        count = len(self.favorites_manager.get_all())
        count_label = QLabel(f"총 {count}개의 즐겨찾기")
        count_label.setStyleSheet(f"color: {t['text_muted']}; font-size: 13px;")
        layout.addWidget(count_label)
        self.count_label = count_label
        
        # 리스트 위젯
        self.list_widget = QListWidget()
        self.list_widget.setAlternatingRowColors(True)
        self._refresh_list()
        layout.addWidget(self.list_widget, 1)
        
        # 버튼 영역
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        # 복사 버튼
        copy_btn = QPushButton("📋 복사")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['accent']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {t['accent_hover']};
            }}
        """)
        copy_btn.clicked.connect(self._copy_selected)
        btn_layout.addWidget(copy_btn)
        
        # QR 버튼
        qr_btn = QPushButton("📱 QR")
        qr_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        qr_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['success']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['success_light']}; color: {t['success']}; }}
        """)
        qr_btn.clicked.connect(self._show_selected_qr)
        btn_layout.addWidget(qr_btn)
        
        # 삭제 버튼
        delete_btn = QPushButton("🗑️ 삭제")
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['danger']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #C0392B;
            }}
        """)
        delete_btn.clicked.connect(self._delete_selected)
        btn_layout.addWidget(delete_btn)
        
        btn_layout.addStretch()
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['neutral']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {t['bg_tertiary']};
                color: {t['text_primary']};
            }}
        """)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def _apply_theme(self):
        """테마 적용"""
        t = ThemeManager.get_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t['bg_primary']};
            }}
            QListWidget {{
                background-color: {t['bg_secondary']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                padding: 5px;
            }}
            QListWidget::item {{
                padding: 12px;
                border-radius: 6px;
                font-size: 14px;
                color: {t['text_primary']};
            }}
            QListWidget::item:alternate {{
                background-color: {t['result_row_alt']};
            }}
            QListWidget::item:selected {{
                background-color: {t['accent_light']};
                color: {t['accent']};
            }}
            QListWidget::item:hover {{
                background-color: {t['bg_hover']};
            }}
        """)
    
    def _refresh_list(self):
        """리스트 새로고침"""
        self.list_widget.clear()
        for fav in self.favorites_manager.get_all():
            numbers_str = " - ".join(f"{n:02d}" for n in fav['numbers'])
            created = fav.get('created_at', '')[:10]
            memo = fav.get('memo', '')
            
            display_text = f"🎱  {numbers_str}"
            if memo:
                display_text += f"  ({memo})"
            display_text += f"  [{created}]"
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, fav['numbers'])
            self.list_widget.addItem(item)
        
        # 카운트 업데이트
        if hasattr(self, 'count_label'):
            self.count_label.setText(f"총 {len(self.favorites_manager.get_all())}개의 즐겨찾기")
    
    def _copy_selected(self):
        """선택된 번호 복사"""
        row = self.list_widget.currentRow()
        if row >= 0:
            item = self.list_widget.item(row)
            if item is None:
                QMessageBox.warning(self, "선택 필요", "선택한 항목을 찾을 수 없습니다.")
                return
            raw_numbers = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(raw_numbers, list):
                QMessageBox.warning(self, "오류", "번호 데이터 형식이 올바르지 않습니다.")
                return
            numbers = [int(n) for n in raw_numbers]
            nums_str = " ".join(f"{n:02d}" for n in numbers)
            clipboard = QApplication.clipboard()
            if clipboard is None:
                QMessageBox.warning(self, "오류", "클립보드를 사용할 수 없습니다.")
                return
            clipboard.setText(nums_str)
            QMessageBox.information(self, "복사 완료", f"번호가 클립보드에 복사되었습니다:\n{nums_str}")
        else:
            QMessageBox.warning(self, "선택 필요", "복사할 항목을 선택하세요.")
    
    def _delete_selected(self):
        """선택 항목 삭제 (확인 다이얼로그)"""
        row = self.list_widget.currentRow()
        if row >= 0:
            reply = QMessageBox.question(
                self, 
                "삭제 확인", 
                "선택한 즐겨찾기를 삭제하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.favorites_manager.remove(row)
                self._refresh_list()
        else:
            QMessageBox.warning(self, "선택 필요", "삭제할 항목을 선택하세요.")

    def _show_selected_qr(self):
        """선택된 번호의 QR 코드 표시"""
        row = self.list_widget.currentRow()
        if row >= 0:
            item = self.list_widget.item(row)
            if item is None:
                QMessageBox.warning(self, "선택 필요", "선택한 항목을 찾을 수 없습니다.")
                return
            raw_numbers = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(raw_numbers, list):
                QMessageBox.warning(self, "오류", "번호 데이터 형식이 올바르지 않습니다.")
                return
            numbers = [int(n) for n in raw_numbers]
            dialog = QRCodeDialog(numbers, self)
            dialog.exec()
        else:
            QMessageBox.warning(self, "선택 필요", "QR 코드를 볼 항목을 선택하세요.")


from klotto.net.client import LottoNetworkManager

# ============================================================
# 실제 당첨 번호 통계 다이얼로그
# ============================================================
class RealStatsDialog(QDialog):
    """실제 당첨 번호 통계 다이얼로그"""
    
    def __init__(self, stats_manager: WinningStatsManager, parent=None):
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
        
        t = ThemeManager.get_theme()
        
        # 헤더 & 동기화 버튼
        header_layout = QHBoxLayout()
        header_label = QLabel("📊 당첨 번호 통계")
        header_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {t['text_primary']};")
        header_layout.addWidget(header_label)
        
        header_layout.addStretch()
        
        self.sync_btn = QPushButton("🔄 최근 5회 동기화")
        self.sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sync_btn.clicked.connect(self._sync_recent_data)
        self.sync_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['accent']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['accent_hover']}; }}
        """)
        header_layout.addWidget(self.sync_btn)
        layout.addLayout(header_layout)
        
        # 진행 상태 표시 줄
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(f"color: {t['accent']}; font-weight: bold;")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)
        
        # 통계 데이터 가져오기
        analysis = self.stats_manager.get_frequency_analysis()
        range_dist = self.stats_manager.get_range_distribution()
        recent = self.stats_manager.get_recent_trend(5)
        
        if not analysis:
            # 데이터 없음 안내
            no_data_label = QLabel("📊 아직 수집된 당첨 데이터가 없습니다.\n\n"
                                   "당첨 정보 위젯에서 회차를 조회하면\n"
                                   "자동으로 통계가 수집됩니다.")
            no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_data_label.setStyleSheet(f"color: {t['text_muted']}; font-size: 15px;")
            layout.addWidget(no_data_label)
            
            close_btn = QPushButton("닫기")
            close_btn.clicked.connect(self.close)
            layout.addWidget(close_btn)
            return
        
        # 통계 요약
        summary_label = QLabel(f"📊 총 {analysis['total_draws']}회차 분석 결과")
        summary_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {t['accent']};")
        layout.addWidget(summary_label)
        
        # 핫 넘버 그룹
        hot_group = QGroupBox("🔥 핫 넘버 TOP 10 (가장 많이 나온 번호)")
        hot_layout = QHBoxLayout(hot_group)
        hot_layout.setSpacing(8)
        
        for num, count in analysis['hot_numbers']:
            ball = LottoBall(num, size=36)
            hot_layout.addWidget(ball)
            count_label = QLabel(f"({count})")
            count_label.setStyleSheet(f"color: {t['text_muted']}; font-size: 11px;")
            hot_layout.addWidget(count_label)
        
        hot_layout.addStretch()
        layout.addWidget(hot_group)
        
        # 콜드 넘버 그룹
        cold_group = QGroupBox("❄️ 콜드 넘버 (가장 적게 나온 번호)")
        cold_layout = QHBoxLayout(cold_group)
        cold_layout.setSpacing(8)
        
        for num, count in analysis['cold_numbers']:
            ball = LottoBall(num, size=36)
            cold_layout.addWidget(ball)
            count_label = QLabel(f"({count})")
            count_label.setStyleSheet(f"color: {t['text_muted']}; font-size: 11px;")
            cold_layout.addWidget(count_label)
        
        cold_layout.addStretch()
        layout.addWidget(cold_group)
        
        # 번호대별 분포
        if range_dist:
            range_group = QGroupBox("📊 번호대별 분포")
            range_layout = QVBoxLayout(range_group)
            
            total_nums = sum(range_dist.values())
            
            for range_name, count in range_dist.items():
                pct = (count / total_nums * 100) if total_nums > 0 else 0
                row_layout = QHBoxLayout()
                
                range_label = QLabel(f"{range_name}:")
                range_label.setFixedWidth(60)
                range_label.setStyleSheet(f"font-weight: bold; color: {t['text_primary']};")
                
                # 프로그레스 바 효과 (텍스트)
                bar_width = int(pct * 2)
                bar = QLabel("█" * bar_width)
                bar.setStyleSheet(f"color: {t['accent']};")
                
                pct_label = QLabel(f"{count}회 ({pct:.1f}%)")
                pct_label.setStyleSheet(f"color: {t['text_secondary']};")
                
                row_layout.addWidget(range_label)
                row_layout.addWidget(bar)
                row_layout.addWidget(pct_label)
                row_layout.addStretch()
                
                range_layout.addLayout(row_layout)
            
            layout.addWidget(range_group)
        
        # 최근 당첨 번호
        if recent:
            recent_group = QGroupBox("📅 최근 당첨 번호")
            recent_layout = QVBoxLayout(recent_group)
            
            for data in recent[:5]:
                row = QHBoxLayout()
                draw_label = QLabel(f"#{data['draw_no']}회")
                draw_label.setFixedWidth(70)
                draw_label.setStyleSheet(f"font-weight: bold; color: {t['accent']};")
                row.addWidget(draw_label)
                
                for num in data['numbers']:
                    ball = LottoBall(num, size=30)
                    row.addWidget(ball)
                
                # 보너스
                plus_label = QLabel("+")
                plus_label.setStyleSheet(f"color: {t['text_muted']};")
                row.addWidget(plus_label)
                
                bonus_ball = LottoBall(data['bonus'], size=30, highlighted=True)
                row.addWidget(bonus_ball)
                
                row.addStretch()
                recent_layout.addLayout(row)
            
            layout.addWidget(recent_group)
        
        layout.addStretch()
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.setMinimumHeight(40)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
    
    def _apply_theme(self):
        t = ThemeManager.get_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t['bg_primary']};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {t['border']};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: {t['bg_secondary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                padding: 0 8px;
            }}
            QPushButton {{
                background-color: {t['accent']};
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                padding: 10px;
            }}
            QPushButton:hover {{
                background-color: {t['accent_hover']};
            }}
        """)
    
    def _sync_recent_data(self):
        """최신 데이터 동기화"""
        # 최신 회차 추정 (LottoApp/WinningInfoWidget 로직과 동일)
        base_date = datetime.date(2002, 12, 7)
        today = datetime.date.today()
        days_diff = (today - base_date).days
        estimated_draw = days_diff // 7 + 1
        now = datetime.datetime.now()
        if today.weekday() == 5 and now.hour < 21:
            estimated_draw -= 1
            
        start_draw = max(1, estimated_draw - 4) # 최근 5개
        draws = list(range(start_draw, estimated_draw + 1))
        
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

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _on_data_received(self, data):
        """데이터 수신 시 처리"""
        try:
            draw_no = self._safe_int(data.get('drwNo'))
            if draw_no > 0:
                numbers = [
                    self._safe_int(data.get('drwtNo1')), self._safe_int(data.get('drwtNo2')),
                    self._safe_int(data.get('drwtNo3')), self._safe_int(data.get('drwtNo4')),
                    self._safe_int(data.get('drwtNo5')), self._safe_int(data.get('drwtNo6'))
                ]
                bonus = self._safe_int(data.get('bnusNo'))
                draw_date_raw = data.get('drwNoDate')
                draw_date = draw_date_raw if isinstance(draw_date_raw, str) else None

                if any(n <= 0 for n in numbers) or bonus <= 0:
                    return
                
                saved = self.stats_manager.add_winning_data(draw_no, numbers, bonus, draw_date=draw_date)
                if saved:
                    self.progress_label.setText(f"{draw_no}회차 저장 완료")
                else:
                    self.progress_label.setText(f"{draw_no}회차는 이미 존재하거나 저장에 실패했습니다.")
                
                # UI 새로고침 효과를 위해... 다이얼로그를 닫고 다시 열라고 안내하거나
                # 혹은 그냥 저장되었다고만 표시
                
        except Exception as e:
            logger.error(f"Sync error: {e}")
        finally:
            self._complete_sync_step()

    def _on_error(self, msg: str):
        """에러 발생 시"""
        self.progress_label.setText(f"오류: {msg}")
        self._complete_sync_step()


# ============================================================
# 당첨 확인 자동화 다이얼로그
# ============================================================
class WinningCheckDialog(QDialog):
    """당첨 확인 자동화 다이얼로그"""
    
    def __init__(self, favorites_manager: FavoritesManager, 
                 history_manager: HistoryManager,
                 stats_manager: WinningStatsManager,
                 parent=None,
                 qr_payload: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.favorites_manager = favorites_manager
        self.history_manager = history_manager
        self.stats_manager = stats_manager
        self.qr_payload = qr_payload
        self._pending_qr_payload: Optional[Dict[str, Any]] = None
        self._qr_network_manager: Optional["LottoNetworkManager"] = None

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
        
        t = ThemeManager.get_theme()
        
        # 설명
        desc_text = "저장된 번호가 과거 당첨 번호와 일치하는지 확인합니다."
        if self.qr_payload:
            desc_text = "QR 스캔 번호를 해당 회차 당첨 번호와 즉시 비교합니다."
        desc_label = QLabel(desc_text)
        desc_label.setStyleSheet(f"color: {t['text_secondary']}; font-size: 14px;")
        layout.addWidget(desc_label)
        
        # 번호 선택
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
        
        # 확인 버튼
        self.check_btn = QPushButton("🔍 당첨 확인 실행")
        self.check_btn.setMinimumHeight(45)
        self.check_btn.clicked.connect(self._run_check)
        layout.addWidget(self.check_btn)
        
        # 결과 영역
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
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.setMinimumHeight(40)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
    
    def _update_number_list(self):
        self.number_list.clear()
        
        if self.source_combo.currentIndex() == 0:
            # 즐겨찾기
            for fav in self.favorites_manager.get_all():
                nums = fav.get('numbers', [])
                memo = fav.get('memo', '')
                text = f"{', '.join(map(str, nums))}"
                if memo:
                    text += f" ({memo})"
                self.number_list.addItem(text)
        else:
            # 히스토리
            for hist in self.history_manager.get_recent(50):
                nums = hist.get('numbers', [])
                text = f"{', '.join(map(str, nums))}"
                self.number_list.addItem(text)

    @staticmethod
    def _normalize_numbers(value: Any) -> Optional[List[int]]:
        if not isinstance(value, list):
            return None
        try:
            numbers = sorted(int(v) for v in value)
        except (TypeError, ValueError):
            return None

        if len(numbers) != 6 or len(set(numbers)) != 6:
            return None
        if any(n < 1 or n > 45 for n in numbers):
            return None
        return numbers

    @staticmethod
    def _calculate_rank(match_count: int, bonus_matched: bool) -> Optional[int]:
        if match_count == 6:
            return 1
        if match_count == 5 and bonus_matched:
            return 2
        if match_count == 5:
            return 3
        if match_count == 4:
            return 4
        if match_count == 3:
            return 5
        return None

    def _clear_results(self):
        while self.result_inner_layout.count():
            item = self.result_inner_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_info_result(self, text: str, color: Optional[str] = None):
        t = ThemeManager.get_theme()
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {color or t['text_muted']}; padding: 20px;")
        self.result_inner_layout.addWidget(label)

    def _build_result_row(
        self,
        header_text: str,
        my_numbers: Set[int],
        winning_numbers: Set[int],
        bonus: int,
    ) -> Tuple[QFrame, int, bool, Optional[int]]:
        t = ThemeManager.get_theme()
        matched = my_numbers & winning_numbers
        match_count = len(matched)
        bonus_matched = bonus in my_numbers
        rank = self._calculate_rank(match_count, bonus_matched)

        result_row = QFrame()
        result_row.setStyleSheet(f"""
            QFrame {{
                background-color: {t['bg_secondary']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                padding: 10px;
            }}
        """)
        row_layout = QVBoxLayout(result_row)

        header = QHBoxLayout()
        draw_label = QLabel(header_text)
        draw_label.setStyleSheet(f"font-weight: bold; color: {t['accent']};")
        header.addWidget(draw_label)

        if rank:
            rank_label = QLabel(f"🎉 {rank}등")
            rank_colors = {1: '#FF0000', 2: '#FF6600', 3: '#FFCC00', 4: '#00CC00', 5: '#0066CC'}
            rank_label.setStyleSheet(f"font-weight: bold; color: {rank_colors.get(rank, t['text_primary'])};")
        else:
            rank_label = QLabel("미당첨")
            rank_label.setStyleSheet(f"font-weight: bold; color: {t['text_muted']};")
        header.addWidget(rank_label)

        match_text = f"일치: {match_count}개"
        if bonus_matched:
            match_text += " + 보너스"
        match_label = QLabel(match_text)
        match_label.setStyleSheet(f"color: {t['text_secondary']};")
        header.addWidget(match_label)
        header.addStretch()
        row_layout.addLayout(header)

        my_nums_layout = QHBoxLayout()
        my_nums_layout.addWidget(QLabel("내 번호:"))
        for num in sorted(my_numbers):
            ball = LottoBall(num, size=30, highlighted=(num in matched))
            my_nums_layout.addWidget(ball)
        my_nums_layout.addStretch()
        row_layout.addLayout(my_nums_layout)

        win_nums_layout = QHBoxLayout()
        win_nums_layout.addWidget(QLabel("당첨 번호:"))
        for num in sorted(winning_numbers):
            ball = LottoBall(num, size=30, highlighted=(num in matched))
            win_nums_layout.addWidget(ball)
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
        
        t = ThemeManager.get_theme()
        
        # 선택된 번호 가져오기
        row = self.number_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "선택 필요", "확인할 번호를 선택하세요.")
            return
        
        if self.source_combo.currentIndex() == 0:
            data = self.favorites_manager.get_all()
        else:
            data = self.history_manager.get_recent(50)
        
        if row >= len(data):
            return
        
        normalized = self._normalize_numbers(data[row].get('numbers', []))
        if not normalized:
            self._add_info_result("선택한 번호 데이터 형식이 올바르지 않습니다.", t['danger'])
            return
        my_numbers = set(normalized)
        
        # 저장된 당첨 데이터로 확인
        winning_data = self.stats_manager.winning_data
        
        if not winning_data:
            self._add_info_result("확인할 당첨 데이터가 없습니다.\n당첨 정보 위젯에서 회차를 조회해 주세요.")
            return
        
        found_any = False
        
        for win_data in winning_data:
            draw_no = int(win_data['draw_no'])
            winning_nums = set(win_data['numbers'])
            bonus = int(win_data['bonus'])
            
            # 비교 
            result_row, match_count, _, _ = self._build_result_row(
                f"#{draw_no}회",
                my_numbers,
                winning_nums,
                bonus
            )
            
            # 3개 이상 일치 시 표시 (5등 이상)
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
            normalized = self._normalize_numbers(entry)
            if normalized:
                normalized_sets.append(normalized)

        if not normalized_sets:
            return None

        return {"draw_no": draw_no, "sets": normalized_sets}

    def _run_qr_payload_check(self):
        self._clear_results()
        normalized_payload = self._normalize_qr_payload(self.qr_payload or {})
        if not normalized_payload:
            self._add_info_result("QR 데이터 형식이 올바르지 않습니다.", ThemeManager.get_theme()['danger'])
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

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _on_qr_draw_loaded(self, data: dict):
        if not self._pending_qr_payload:
            return

        expected_draw = self._pending_qr_payload["draw_no"]
        draw_no = self._safe_int(data.get("drwNo"))
        if draw_no != expected_draw:
            self._on_qr_draw_error("요청한 회차와 다른 응답이 수신되었습니다.")
            return

        numbers = [
            self._safe_int(data.get('drwtNo1')),
            self._safe_int(data.get('drwtNo2')),
            self._safe_int(data.get('drwtNo3')),
            self._safe_int(data.get('drwtNo4')),
            self._safe_int(data.get('drwtNo5')),
            self._safe_int(data.get('drwtNo6')),
        ]
        bonus = self._safe_int(data.get('bnusNo'))
        draw_date_raw = data.get('drwNoDate')
        draw_date = draw_date_raw if isinstance(draw_date_raw, str) else None

        if any(n < 1 or n > 45 for n in numbers) or bonus < 1 or bonus > 45:
            self._on_qr_draw_error("QR 회차 데이터 형식이 올바르지 않습니다.")
            return

        self.stats_manager.add_winning_data(draw_no, numbers, bonus, draw_date=draw_date)
        draw_data = self.stats_manager.get_draw_data(expected_draw)
        if not draw_data:
            self._on_qr_draw_error("QR 회차 데이터를 저장했지만 조회에 실패했습니다.")
            return

        self._render_qr_results(self._pending_qr_payload, draw_data)
        self._pending_qr_payload = None
        self.check_btn.setEnabled(True)

    def _on_qr_draw_error(self, msg: str):
        self._clear_results()
        self._add_info_result(f"QR 회차 데이터를 가져오지 못했습니다.\n{msg}", ThemeManager.get_theme()['danger'])
        self._pending_qr_payload = None
        self.check_btn.setEnabled(True)

    def _render_qr_results(self, payload: Dict[str, Any], draw_data: Dict[str, Any]):
        self._clear_results()
        draw_no = int(draw_data.get("draw_no", payload["draw_no"]))
        draw_date = draw_data.get("date", "")
        if draw_date:
            self._add_info_result(f"기준 회차: {draw_no}회 ({draw_date})", ThemeManager.get_theme()['accent'])
        else:
            self._add_info_result(f"기준 회차: {draw_no}회", ThemeManager.get_theme()['accent'])

        winning_numbers = set(draw_data.get("numbers", []))
        bonus = int(draw_data.get("bonus", 0))
        if len(winning_numbers) != 6 or bonus < 1 or bonus > 45:
            self._add_info_result("저장된 당첨 데이터가 올바르지 않습니다.", ThemeManager.get_theme()['danger'])
            self.check_btn.setEnabled(True)
            return

        for idx, numbers in enumerate(payload["sets"], start=1):
            result_row, _, _, _ = self._build_result_row(
                f"#{draw_no}회 | QR 게임 {idx}",
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
        t = ThemeManager.get_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t['bg_primary']};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {t['border']};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: {t['bg_secondary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                padding: 0 8px;
            }}
            QPushButton {{
                background-color: {t['accent']};
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                padding: 10px;
            }}
            QPushButton:hover {{
                background-color: {t['accent_hover']};
            }}
            QComboBox {{
                padding: 8px;
                border: 1px solid {t['border']};
                border-radius: 6px;
                background-color: {t['bg_secondary']};
            }}
            QListWidget {{
                border: 1px solid {t['border']};
                border-radius: 6px;
                background-color: {t['bg_secondary']};
            }}
        """)


# ============================================================
# 데이터 내보내기/가져오기 다이얼로그
# ============================================================
class ExportImportDialog(QDialog):
    """데이터 내보내기/가져오기 다이얼로그"""
    
    def __init__(self, favorites_manager: FavoritesManager, 
                 history_manager: HistoryManager, stats_manager: WinningStatsManager, parent=None):
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
        
        t = ThemeManager.get_theme()
        
        # 내보내기 그룹
        export_group = QGroupBox("📤 내보내기")
        export_layout = QVBoxLayout(export_group)
        
        # 데이터 유형 선택
        data_layout = QHBoxLayout()
        data_layout.addWidget(QLabel("데이터 선택:"))
        self.data_combo = QComboBox()
        self.data_combo.addItems(["즐겨찾기", "히스토리", "당첨 통계"])
        data_layout.addWidget(self.data_combo)
        data_layout.addStretch()
        export_layout.addLayout(data_layout)
        
        # 형식 선택
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("형식:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["CSV", "JSON"])
        format_layout.addWidget(self.format_combo)
        format_layout.addStretch()
        export_layout.addLayout(format_layout)
        
        # 내보내기 버튼
        export_btn = QPushButton("💾 내보내기")
        export_btn.clicked.connect(self._export_data)
        export_layout.addWidget(export_btn)
        
        layout.addWidget(export_group)
        
        # 가져오기 그룹
        import_group = QGroupBox("📥 가져오기")
        import_layout = QVBoxLayout(import_group)
        
        import_desc = QLabel("JSON 파일에서 데이터를 가져옵니다.\n기존 데이터에 병합됩니다.")
        import_desc.setStyleSheet(f"color: {t['text_muted']}; font-size: 12px;")
        import_layout.addWidget(import_desc)
        
        # 가져오기 대상 선택
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
        
        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.setMinimumHeight(40)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    @staticmethod
    def _normalize_numbers(value: Any) -> Optional[List[int]]:
        if not isinstance(value, (list, tuple)):
            return None

        try:
            numbers = sorted(int(n) for n in value)
        except (TypeError, ValueError):
            return None

        if len(numbers) != 6 or len(set(numbers)) != 6:
            return None
        if any(n < 1 or n > 45 for n in numbers):
            return None
        return numbers

    @staticmethod
    def _normalize_positive_int(value: Any) -> Optional[int]:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _normalize_bonus(value: Any, numbers: List[int]) -> Optional[int]:
        bonus = ExportImportDialog._normalize_positive_int(value)
        if bonus is None:
            return None
        if bonus < 1 or bonus > 45 or bonus in numbers:
            return None
        return bonus
    
    def _export_data(self):
        data_type_idx = self.data_combo.currentIndex()
        format_idx = self.format_combo.currentIndex()
        
        # 데이터 가져오기
        if data_type_idx == 0:
            data = self.favorites_manager.get_all()
            data_type = 'favorites'
            default_name = 'lotto_favorites'
        elif data_type_idx == 1:
            data = self.history_manager.get_all()
            data_type = 'history'
            default_name = 'lotto_history'
        else:
            data = self.stats_manager.winning_data
            data_type = 'winning_stats'
            default_name = 'lotto_winning_stats'
        
        if not data:
            QMessageBox.warning(self, "데이터 없음", "내보낼 데이터가 없습니다.")
            return
        
        # 파일 저장 다이럴로그
        if format_idx == 0:
            ext = "csv"
            filter_str = "CSV 파일 (*.csv)"
        else:
            ext = "json"
            filter_str = "JSON 파일 (*.json)"
        
        filepath, _ = QFileDialog.getSaveFileName(
            self, "내보내기", f"{default_name}.{ext}", filter_str
        )
        
        if not filepath:
            return
        
        # 내보내기 실행
        success = False
        if format_idx == 0:
            success = DataExporter.export_to_csv(data, filepath, data_type)
        else:
            success = DataExporter.export_to_json(data, filepath)
        
        if success:
            QMessageBox.information(self, "완료", f"{len(data)}개 항목이 저장되었습니다.\n{filepath}")
        else:
            QMessageBox.warning(self, "오류", "내보내기에 실패했습니다.")
    
    def _import_data(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "가져오기", "", "JSON 파일 (*.json)"
        )
        
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
            # 즐겨찾기에 추가
            items_to_add: List[Dict[str, Any]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                numbers = self._normalize_numbers(item.get('numbers'))
                if not numbers:
                    continue
                memo = item.get('memo', '')
                if not isinstance(memo, str):
                    memo = str(memo)
                items_to_add.append({'numbers': numbers, 'memo': memo})
            imported_count = self.favorites_manager.add_many(items_to_add)
        elif target_idx == 1:
            # 히스토리에 추가
            history_sets: List[List[int]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                numbers = self._normalize_numbers(item.get('numbers'))
                if not numbers:
                    continue
                history_sets.append(numbers)
            imported_count = len(self.history_manager.add_many(history_sets))
        else:
            # 당첨 통계에 추가
            existing_draws = {
                d.get('draw_no') for d in self.stats_manager.winning_data if isinstance(d, dict)
            }
            for item in data:
                if not isinstance(item, dict):
                    continue

                draw_no = self._normalize_positive_int(item.get('draw_no'))
                numbers = self._normalize_numbers(item.get('numbers'))
                bonus = self._normalize_bonus(item.get('bonus'), numbers) if numbers else None
                draw_date = item.get('date')
                draw_date_value = draw_date if isinstance(draw_date, str) else None

                if draw_no is None or numbers is None or bonus is None:
                    continue
                if draw_no in existing_draws:
                    continue

                saved = self.stats_manager.add_winning_data(draw_no, numbers, bonus, draw_date=draw_date_value)
                if saved:
                    existing_draws.add(draw_no)
                    imported_count += 1
        
        QMessageBox.information(
            self, "완료", 
            f"{imported_count}개 항목이 가져와졌습니다.\n(중복 항목은 제외됨)"
        )
    
    def _apply_theme(self):
        t = ThemeManager.get_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t['bg_primary']};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {t['border']};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: {t['bg_secondary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                padding: 0 8px;
            }}
            QPushButton {{
                background-color: {t['accent']};
                color: white;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                padding: 10px;
            }}
            QPushButton:hover {{
                background-color: {t['accent_hover']};
            }}
            QComboBox {{
                padding: 8px;
                border: 1px solid {t['border']};
                border-radius: 6px;
                background-color: {t['bg_secondary']};
            }}
        """)
