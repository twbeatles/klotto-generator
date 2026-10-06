import sys
import traceback
from pathlib import Path
from typing import Optional
from PyQt6.QtCore import QLockFile
from PyQt6.QtWidgets import QApplication, QMessageBox
from .config import APP_CONFIG
from .utils import logger
from .ui.main_window import LottoApp

_app_lock: Optional[QLockFile] = None


def acquire_app_lock(lock_dir: Optional[Path] = None) -> bool:
    """단일 인스턴스 실행을 보장하는 락을 획득한다. 성공 시 True.

    이미 살아 있는 인스턴스가 락을 쥐고 있으면 False를 반환한다.
    크래시로 남은 락(소유 프로세스 사망)은 QLockFile이 감지해 회수하므로
    정상 종료 여부와 관계없이 다음 실행이 막히지 않는다.
    """
    global _app_lock
    try:
        target_dir = Path(lock_dir) if lock_dir is not None else Path(APP_CONFIG['APP_DATA_DIR'])
        target_dir.mkdir(parents=True, exist_ok=True)
        candidate = QLockFile(str(target_dir / 'app.lock'))
        if candidate.tryLock():
            _app_lock = candidate
            return True
        return False
    except Exception:
        logger.exception('Failed to acquire app lock; starting without single-instance guard')
        return True


def release_app_lock() -> None:
    global _app_lock
    try:
        if _app_lock is not None:
            _app_lock.unlock()
    except Exception:
        pass
    finally:
        _app_lock = None

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

    if not acquire_app_lock():
        QMessageBox.warning(
            None,
            '이미 실행 중',
            '프로그램이 이미 실행 중입니다.\n실행 중인 창을 확인해 주세요.',
        )
        return
    
    # 폰트 설정 (윈도우의 경우 맑은 고딕 등)
    from PyQt6.QtGui import QFont
    font = QFont("Malgun Gothic", 10)
    app.setFont(font)
    
    logger.info(f"Starting {APP_CONFIG['APP_NAME']} v{APP_CONFIG['VERSION']}")
    logger.info(f"Data directory: {APP_CONFIG['FAVORITES_FILE'].parent}")
    
    window = LottoApp()
    window.show()

    try:
        window.start_sync()
        logger.info("Background sync started")
    except Exception as e:
        logger.warning(f"Background sync failed to start: {e}")
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()

