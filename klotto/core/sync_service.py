"""
로또 당첨 정보 백그라운드 동기화 서비스
앱 시작 시 최신 당첨 정보를 DB에 자동 업데이트
"""
import sqlite3
import urllib.request
import json
from pathlib import Path
from typing import Any, Dict, Optional, cast
from PyQt6.QtCore import QThread, pyqtSignal
from klotto.config import APP_CONFIG
from klotto.utils import logger


class LottoSyncWorker(QThread):
    """백그라운드에서 최신 당첨 정보를 동기화하는 워커"""
    finished = pyqtSignal(int)  # 동기화된 회차 수
    error = pyqtSignal(str)
    
    API_URL = "https://www.dhlottery.co.kr/lt645/selectPstLt645Info.do?srchLtEpsd={}"
    
    def __init__(self, db_path: Path):
        super().__init__()
        self.db_path = db_path
        self._is_cancelled = False
    
    def cancel(self):
        self._is_cancelled = True
    
    def _get_last_draw_no(self) -> int:
        """DB에서 마지막 회차 번호 조회"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT MAX(draw_no) FROM draws')
                result = cursor.fetchone()
            return result[0] if result[0] else 0
        except sqlite3.OperationalError:
            return 0
        except Exception as e:
            logger.error(f"Failed to read last draw number: {e}")
            return 0
    
    def _estimate_current_draw(self) -> int:
        """현재 회차 추정"""
        import datetime
        base_date = datetime.date(2002, 12, 7)
        today = datetime.date.today()
        days_diff = (today - base_date).days
        estimated = days_diff // 7 + 1
        
        # 토요일 21시 전이면 이전 회차
        now = datetime.datetime.now()
        if today.weekday() == 5 and now.hour < 21:
            estimated -= 1
        return estimated
    
    def _fetch_draw(self, draw_no: int) -> Optional[Dict[str, Any]]:
        """API에서 회차 정보 가져오기"""
        try:
            url = self.API_URL.format(draw_no)
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.dhlottery.co.kr/lt645/result',
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
            })
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = response.read().decode('utf-8')
                result = json.loads(data)
                
                # 새 API 형식 처리
                if 'data' in result and 'list' in result['data']:
                    item = result['data']['list'][0]
                    date_str = str(item.get('ltRflYmd', ''))
                    if len(date_str) == 8:
                        date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                    
                    return {
                        'draw_no': item.get('ltEpsd'),
                        'date': date_str,
                        'num1': item.get('tm1WnNo'),
                        'num2': item.get('tm2WnNo'),
                        'num3': item.get('tm3WnNo'),
                        'num4': item.get('tm4WnNo'),
                        'num5': item.get('tm5WnNo'),
                        'num6': item.get('tm6WnNo'),
                        'bonus': item.get('bnsWnNo'),
                        'prize_amount': item.get('rnk1WnAmt', 0),
                        'winners_count': item.get('rnk1WnNope', 0),
                        'total_sales': item.get('rlvtEpsdSumNtslAmt', 0),
                    }
                return None
        except Exception as e:
            logger.error(f"Fetch error for draw {draw_no}: {e}")
            return None
    
    def _save_draw(self, data: Dict[str, Any]) -> bool:
        """DB에 회차 저장"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 테이블 생성 (없으면)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS draws (
                        draw_no INTEGER PRIMARY KEY,
                        date TEXT,
                        num1 INTEGER, num2 INTEGER, num3 INTEGER,
                        num4 INTEGER, num5 INTEGER, num6 INTEGER,
                        bonus INTEGER,
                        prize_amount INTEGER,
                        winners_count INTEGER,
                        total_sales INTEGER
                    )
                ''')

                cursor.execute('''
                    INSERT OR REPLACE INTO draws 
                    (draw_no, date, num1, num2, num3, num4, num5, num6, bonus, prize_amount, winners_count, total_sales)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    data['draw_no'], data['date'],
                    data['num1'], data['num2'], data['num3'],
                    data['num4'], data['num5'], data['num6'],
                    data['bonus'], data['prize_amount'],
                    data['winners_count'], data['total_sales']
                ))

                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Save error: {e}")
            return False
    
    def run(self):
        """동기화 실행"""
        if not self.db_path:
            self.error.emit("DB 경로가 설정되지 않았습니다.")
            return
            
        # DB 디렉토리 생성
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        last_draw = self._get_last_draw_no()
        current_draw = self._estimate_current_draw()
        
        if last_draw >= current_draw:
            logger.info(f"DB is up to date (last: {last_draw})")
            self.finished.emit(0)
            return
        
        synced_count = 0
        
        for draw_no in range(last_draw + 1, current_draw + 1):
            if self._is_cancelled:
                break
                
            data = self._fetch_draw(draw_no)
            if data and data.get('draw_no'):
                if self._save_draw(data):
                    synced_count += 1
                    logger.info(f"Synced draw #{draw_no}")
            
            self.msleep(200)  # API 부하 방지
        
        self.finished.emit(synced_count)


def start_background_sync(stats_manager=None) -> Optional[LottoSyncWorker]:
    """백그라운드 동기화 시작 (호출자가 워커 참조 유지 필요)"""
    db_path = cast(Path, APP_CONFIG.get('LOTTO_HISTORY_DB'))
    if not db_path:
        return None
    
    worker = LottoSyncWorker(db_path)
    
    def on_finished(count):
        if count > 0:
            logger.info(f"Background sync completed: {count} draws added")
            if stats_manager:
                stats_manager.reload_from_db()
    
    worker.finished.connect(on_finished)
    worker.start()
    
    return worker
