import cv2
import numpy as np
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QMessageBox, QFileDialog, QComboBox, QFrame
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QImage, QPixmap

from klotto.utils import logger, ThemeManager
from klotto.qr_utils import parse_lotto_qr_url

# Try importing pyzbar
try:
    from pyzbar.pyzbar import decode
    msg = ""
    HAS_PYZBAR = True
except ImportError:
    HAS_PYZBAR = False
except Exception as e: # Handle dylib issues on some OS
    HAS_PYZBAR = False
    logger.error(f"Failed to import pyzbar: {e}")

class CameraWorker(QThread):
    image_data = pyqtSignal(np.ndarray)
    
    def __init__(self, camera_index=0):
        super().__init__()
        self.camera_index = camera_index
        self.running = False

    def run(self):
        self.running = True
        cap = cv2.VideoCapture(self.camera_index)
        
        while self.running:
            ret, frame = cap.read()
            if ret:
                self.image_data.emit(frame)
            self.msleep(30)
            
        cap.release()

    def stop(self):
        self.running = False
        self.wait()

class QRCodeScannerDialog(QDialog):
    """QR Code Scanner Dialog using OpenCV and Pyzbar"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📷 QR 코드 스캔")
        self.setFixedSize(600, 500)
        
        self.scanned_data = None
        self.camera_worker = None
        
        self._setup_ui()
        self._apply_theme()
        
        if not HAS_PYZBAR:
            QMessageBox.critical(self, "오류", "pyzbar 라이브러리가 필요합니다.\npip install pyzbar opencv-python")
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)
        
        t = ThemeManager.get_theme()
        
        # Viewfinder Area
        self.viewfinder = QLabel()
        self.viewfinder.setFixedSize(560, 360)
        self.viewfinder.setStyleSheet("background-color: black; border-radius: 8px;")
        self.viewfinder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.viewfinder.setText("카메라를 시작하거나 이미지를 불러오세요")
        layout.addWidget(self.viewfinder)
        
        # Controls
        controls = QHBoxLayout()
        
        self.cam_btn = QPushButton("📷 카메라 시작")
        self.cam_btn.clicked.connect(self._toggle_camera)
        controls.addWidget(self.cam_btn)
        
        self.file_btn = QPushButton("📂 이미지 불러오기")
        self.file_btn.clicked.connect(self._load_image)
        controls.addWidget(self.file_btn)
        
        layout.addLayout(controls)
        
        # Status
        self.status_label = QLabel("준비")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet(f"color: {t['text_muted']};")
        layout.addWidget(self.status_label)
        
        # Close
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        # Apply Button Styles
        for btn in [self.cam_btn, self.file_btn, close_btn]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(35)

    def _apply_theme(self):
        t = ThemeManager.get_theme()
        self.setStyleSheet(f"background-color: {t['bg_primary']}; color: {t['text_primary']};")
        
        btn_style = f"""
            QPushButton {{
                background-color: {t['bg_tertiary']};
                color: {t['text_primary']};
                border: 1px solid {t['border']};
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {t['accent_light']};
                color: {t['accent']};
            }}
        """
        self.cam_btn.setStyleSheet(btn_style)
        self.file_btn.setStyleSheet(btn_style)

    def _toggle_camera(self):
        if self.camera_worker and self.camera_worker.isRunning():
            self.camera_worker.stop()
            self.cam_btn.setText("📷 카메라 시작")
            self.viewfinder.setText("카메라 중지됨")
        else:
            self.camera_worker = CameraWorker()
            self.camera_worker.image_data.connect(self._update_frame)
            self.camera_worker.start()
            self.cam_btn.setText("⏹ 카메라 중지")

    def _update_frame(self, frame):
        # Convert to Qt Image
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_Qt_format = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        p = convert_to_Qt_format.scaled(560, 360, Qt.AspectRatioMode.KeepAspectRatio)
        self.viewfinder.setPixmap(QPixmap.fromImage(p))
        
        # Try decoding
        self._decode_frame(frame)

    def _decode_frame(self, frame):
        if not HAS_PYZBAR:
            return
            
        decoded_objects = decode(frame)
        for obj in decoded_objects:
            data = obj.data.decode('utf-8')
            if 'dhlottery.co.kr' in data:
                self._handle_result(data)
                if self.camera_worker:
                    self.camera_worker.stop()
                    self.cam_btn.setText("📷 카메라 시작")
                break

    def _load_image(self):
        fname, _ = QFileDialog.getOpenFileName(self, '이미지 열기', '', "Image files (*.jpg *.png *.jpeg)")
        if fname:
            frame = cv2.imread(fname)
            if frame is not None:
                # Show image
                self._update_frame(frame)
                # Decode
                self._decode_frame(frame)
            else:
                QMessageBox.warning(self, "오류", "이미지를 불러올 수 없습니다.")

    def _handle_result(self, url):
        self.status_label.setText("QR 코드 감지됨! 분석 중...")
        try:
            result = parse_lotto_qr_url(url)
            self.scanned_data = result
            
            draw_no = result['draw_no']
            parsed_sets = result['sets']
            
            # Show summary
            msg = f"회차: {draw_no}회\n"
            msg += f"게임 수: {len(parsed_sets)}\n\n"
            msg += "이 번호로 당첨 확인을 진행하시겠습니까?"
            
            reply = QMessageBox.question(self, "스캔 완료", msg, 
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            
            if reply == QMessageBox.StandardButton.Yes:
                self.accept()
            else:
                self.status_label.setText("스캔 취소됨. 다시 시도하세요.")
                if self.camera_worker and not self.camera_worker.isRunning():
                    self.camera_worker.start()
            
        except Exception as e:
            logger.error(f"Parse error: {e}")
            self.status_label.setText("유효하지 않은 로또 QR 코드입니다.")
            if self.camera_worker and not self.camera_worker.isRunning():
                self.camera_worker.start()

    def closeEvent(self, event):
        if self.camera_worker:
            self.camera_worker.stop()
        super().closeEvent(event)
