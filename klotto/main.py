import sys
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox
from .config import APP_CONFIG
from .utils import logger
from .ui.main_window import LottoApp

def exception_hook(exctype, value, traceback_obj):
    """글로벌 예외 처리"""
    traceback_str = ''.join(traceback.format_tb(traceback_obj))
    error_msg = f"{exctype.__name__}: {value}\n\n{traceback_str}"
    logger.critical(f"Uncaught exception:\n{error_msg}")
    
    # GUI가 살아있다면 에러 메시지 표시
    try:
        if QApplication.instance():
            QMessageBox.critical(None, "치명적 오류", 
                               f"예기치 않은 오류가 발생했습니다.\n\n{exctype.__name__}: {value}")
    except:
        pass
    
    sys.__excepthook__(exctype, value, traceback_obj)

def main():
    """애플리케이션 진입점"""
    sys.excepthook = exception_hook
    
    app = QApplication(sys.argv)
    app.setApplicationName(APP_CONFIG['APP_NAME'])
    app.setApplicationVersion(APP_CONFIG['VERSION'])
    
    # 폰트 설정 (윈도우의 경우 맑은 고딕 등)
    from PyQt6.QtGui import QFont
    font = QFont("Malgun Gothic", 10)
    app.setFont(font)
    
    logger.info(f"Starting {APP_CONFIG['APP_NAME']} v{APP_CONFIG['VERSION']}")
    logger.info(f"Data directory: {APP_CONFIG['FAVORITES_FILE'].parent}")
    
    window = LottoApp()
    window.show()
    
    # 백그라운드에서 최신 당첨 정보 동기화 시작
    try:
        from .core.sync_service import start_background_sync
        window._sync_worker = start_background_sync(window.stats_manager)
        if window._sync_worker:
            logger.info("Background sync started")
    except Exception as e:
        logger.warning(f"Background sync failed to start: {e}")
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()

