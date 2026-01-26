import json
import urllib.request
from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal, QObject
from klotto.utils import logger
from klotto.config import DHLOTTERY_API_URL, APP_CONFIG

# ============================================================
# API 워커 (QThread 기반 - 안정적인 urllib 사용)
# ============================================================
class LottoApiWorker(QThread):
    """동행복권 API에서 로또 당첨 정보를 가져오는 워커 스레드"""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, draw_nos: list):
        super().__init__()
        self.draw_nos = draw_nos
        self._is_cancelled = False
    
    def cancel(self):
        self._is_cancelled = True
    
    def _convert_new_format_to_old(self, new_data: dict) -> dict:
        """새 API 응답 형식을 기존 형식으로 변환"""
        # 새 API 형식:
        # { "data": { "list": [{ "ltEpsd": 1205, "tm1WnNo": 1, ... }] } }
        # 기존 형식:
        # { "returnValue": "success", "drwNo": 1205, "drwtNo1": 1, ... }
        
        try:
            data_list = new_data.get('data', {}).get('list', [])
            if not data_list:
                return None
            
            item = data_list[0]  # 첫 번째 항목 사용
            
            return {
                'returnValue': 'success',
                'drwNo': item.get('ltEpsd'),
                'drwNoDate': self._format_date(item.get('ltRflYmd', '')),
                'drwtNo1': item.get('tm1WnNo'),
                'drwtNo2': item.get('tm2WnNo'),
                'drwtNo3': item.get('tm3WnNo'),
                'drwtNo4': item.get('tm4WnNo'),
                'drwtNo5': item.get('tm5WnNo'),
                'drwtNo6': item.get('tm6WnNo'),
                'bnusNo': item.get('bnsWnNo'),
                'firstWinamnt': item.get('rnk1WnAmt', 0),
                'firstPrzwnerCo': item.get('rnk1WnNope', 0),
                'totSellamnt': item.get('rlvtEpsdSumNtslAmt', 0),
            }
        except Exception as e:
            logger.error(f"Error converting new API format: {e}")
            return None
    
    def _format_date(self, date_str: str) -> str:
        """날짜 형식 변환: '20260103' -> '2026-01-03'"""
        if len(date_str) == 8:
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        return date_str
    
    def run(self):
        total = len(self.draw_nos)
        for i, draw_no in enumerate(self.draw_nos):
            if self._is_cancelled:
                return
            
            # 다수의 요청 시 약간의 딜레이 (서버 부하 방지)
            if i > 0:
                self.msleep(200)
                
            try:
                url = DHLOTTERY_API_URL.format(draw_no)
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'https://www.dhlottery.co.kr/lt645/result',
                    'Accept': 'application/json, text/javascript, */*; q=0.01',
                    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
                    'X-Requested-With': 'XMLHttpRequest',
                })
                
                logger.info(f"Requesting draw #{draw_no} from new API")
                
                with urllib.request.urlopen(req, timeout=APP_CONFIG['API_TIMEOUT']) as response:
                    raw_data = response.read().decode('utf-8')
                    
                    if self._is_cancelled:
                        return
                    
                    # 응답이 JSON인지 확인
                    if not raw_data.strip().startswith('{'):
                        logger.error(f"Response is not JSON. First 200 chars: {raw_data[:200]}")
                        self.error.emit(f"{draw_no}회차: 서버 응답 오류")
                        continue
                        
                    new_data = json.loads(raw_data)
                    
                    # 새 형식을 기존 형식으로 변환
                    converted_data = self._convert_new_format_to_old(new_data)
                    
                    if converted_data and converted_data.get('drwNo'):
                        logger.info(f"Successfully fetched draw #{draw_no}")
                        self.finished.emit(converted_data)
                    else:
                        self.error.emit(f"{draw_no}회차 정보를 찾을 수 없습니다.")
                        
            except urllib.error.URLError as e:
                logger.error(f"Network error for #{draw_no}: {e}")
                self.error.emit(f"{draw_no}회차: 네트워크 오류")
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error for #{draw_no}: {e}")
                self.error.emit(f"{draw_no}회차: 데이터 파싱 오류")
            except Exception as e:
                logger.error(f"Unknown error for #{draw_no}: {e}")
                self.error.emit(f"{draw_no}회차: 알 수 없는 오류")


# ============================================================
# 네트워크 매니저 (QThread 워커 관리)
# ============================================================
class LottoNetworkManager(QObject):
    """동행복권 API 통신 관리자 (비동기 QThread 기반)"""
    
    # 외부에서 연결할 수 있는 시그널
    dataLoaded = pyqtSignal(dict)
    errorOccurred = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_worker: Optional[LottoApiWorker] = None
        
    def fetch_draw(self, draw_no: int):
        """단일 회차 정보 요청"""
        self.fetch_draws([draw_no])
        
    def fetch_draws(self, draw_nos: list):
        """여러 회차 정보 요청 (순차적)"""
        # 기존 워커가 실행 중이면 취소
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.cancel()
            self._current_worker.wait(1000)  # 최대 1초 대기
            
        # 새 워커 생성
        self._current_worker = LottoApiWorker(draw_nos)
        
        # 워커 시그널을 매니저 시그널로 연결
        self._current_worker.finished.connect(self.dataLoaded.emit)
        self._current_worker.error.connect(self.errorOccurred.emit)
            
        self._current_worker.start()
        
    def cancel(self):
        """요청 취소"""
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.cancel()
            self._current_worker = None
