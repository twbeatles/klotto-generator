from typing import List

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from klotto.logging import logger
from klotto.ui.theme import ThemeManager

qrcode = None
try:
    import qrcode

    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False


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

        theme = ThemeManager.get_theme()

        nums_str = " ".join(f"{number:02d}" for number in self.numbers)
        info_label = QLabel(f"번호: {nums_str}")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {theme['text_primary']};")
        layout.addWidget(info_label)

        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setFixedSize(200, 200)
        self.qr_label.setStyleSheet("background-color: white; border-radius: 10px;")

        if HAS_QRCODE:
            self._generate_qr()
        else:
            self.qr_label.setText("qrcode 라이브러리가\n설치되지 않았습니다.")

        layout.addWidget(self.qr_label, alignment=Qt.AlignmentFlag.AlignCenter)

        close_btn = QPushButton("닫기")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
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
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.setLayout(layout)

    def _generate_qr(self):
        if not HAS_QRCODE or qrcode is None:
            self.qr_label.setText("qrcode 라이브러리가\n설치되지 않았습니다.")
            return

        try:
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

            import io

            buffer = io.BytesIO()
            img.save(buffer, "PNG")
            qimg = QImage.fromData(buffer.getvalue())
            pixmap = QPixmap.fromImage(qimg)

            self.qr_label.setPixmap(
                pixmap.scaled(
                    180,
                    180,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        except Exception as exc:
            logger.error("QR Code generation failed: %s", exc)
            self.qr_label.setText("QR 생성 실패")

    def _apply_theme(self):
        theme = ThemeManager.get_theme()
        self.setStyleSheet(f"background-color: {theme['bg_primary']};")
