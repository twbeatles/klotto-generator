import json
import datetime
import os
import sqlite3
from pathlib import Path
from typing import Any, List, Dict, Optional, Tuple, cast
from klotto.config import APP_CONFIG
from klotto.utils import logger

# ============================================================
# 역대 당첨 번호 통계 관리
# ============================================================
class WinningStatsManager:
    """역대 당첨 번호 통계 관리 (SQLite DB 우선, JSON 폴백)"""
    
    def __init__(self):
        self.stats_file: Path = cast(Path, APP_CONFIG['WINNING_STATS_FILE'])
        self.db_path: Path = cast(Path, APP_CONFIG['LOTTO_HISTORY_DB'])
        self.winning_data: List[Dict[str, Any]] = []
        self._load()
    
    def _load(self):
        """데이터 로드 - DB 우선, JSON 폴백"""
        # 먼저 SQLite DB에서 로드 시도
        if self.db_path and self.db_path.exists():
            if self._load_from_db():
                return
        
        # DB가 없으면 JSON 파일에서 로드
        self._load_from_json()
    
    def _load_from_db(self) -> bool:
        """SQLite DB에서 데이터 로드"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT draw_no, date, num1, num2, num3, num4, num5, num6, bonus 
                    FROM draws 
                    ORDER BY draw_no DESC
                ''')
                rows = cursor.fetchall()
            
            if not rows:
                return False
            
            self.winning_data = []
            invalid_count = 0
            for row in rows:
                normalized = self._normalize_draw_input(row[0], [row[2], row[3], row[4], row[5], row[6], row[7]], row[8])
                if not normalized:
                    invalid_count += 1
                    continue

                draw_no, numbers, bonus = normalized
                self.winning_data.append({
                    'draw_no': draw_no,
                    'date': row[1] or '',
                    'numbers': numbers,
                    'bonus': bonus
                })

            if invalid_count:
                logger.warning(f"Skipped {invalid_count} invalid winning records from DB")

            if not self.winning_data:
                return False
            
            logger.info(f"Loaded {len(self.winning_data)} winning records from DB")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load from DB: {e}")
            return False

    def _normalize_draw_input(self, draw_no: int, numbers: List[int], bonus: int) -> Optional[Tuple[int, List[int], int]]:
        """입력 당첨 데이터 정규화 및 검증"""
        try:
            parsed_draw_no = int(draw_no)
            parsed_numbers = sorted(int(n) for n in numbers)
            parsed_bonus = int(bonus)
        except (TypeError, ValueError):
            return None

        if parsed_draw_no <= 0:
            return None
        if len(parsed_numbers) != 6 or len(set(parsed_numbers)) != 6:
            return None
        if any(n < 1 or n > 45 for n in parsed_numbers):
            return None
        if parsed_bonus < 1 or parsed_bonus > 45 or parsed_bonus in parsed_numbers:
            return None

        return parsed_draw_no, parsed_numbers, parsed_bonus

    def _save_to_db(self, draw_no: int, numbers: List[int], bonus: int, draw_date: Optional[str] = None) -> bool:
        """DB에 당첨 데이터 저장 (신규 삽입 시 True)"""
        if not self.db_path:
            return False

        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
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
                    INSERT OR IGNORE INTO draws 
                    (draw_no, date, num1, num2, num3, num4, num5, num6, bonus, prize_amount, winners_count, total_sales)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    draw_no,
                    draw_date or datetime.date.today().isoformat(),
                    numbers[0], numbers[1], numbers[2],
                    numbers[3], numbers[4], numbers[5],
                    bonus,
                    0,
                    0,
                    0,
                ))

                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to save winning stats to DB: {e}")
            return False
    
    def _load_from_json(self):
        """JSON 파일에서 통계 데이터 로드 (폴백)"""
        try:
            if self.stats_file and self.stats_file.exists():
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    self.winning_data = json.load(f)
                logger.info(f"Loaded {len(self.winning_data)} winning records from JSON")
        except Exception as e:
            logger.error(f"Failed to load winning stats: {e}")
            self.winning_data = []
    
    def _save(self):
        """통계 데이터 저장 (JSON - 캐시용)"""
        if not self.stats_file:
            return

        temp_file: Optional[Path] = None
        try:
            self.stats_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file = self.stats_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.winning_data, f, ensure_ascii=False, indent=2)
            # Atomic replacement
            if self.stats_file.exists():
                os.replace(temp_file, self.stats_file)
            else:
                os.rename(temp_file, self.stats_file)
        except Exception as e:
            logger.error(f"Failed to save winning stats: {e}")
            # Clean up temp file if exists
            try:
                if temp_file and temp_file.exists():
                    temp_file.unlink()
            except: pass
    
    def add_winning_data(self, draw_no: int, numbers: List[int], bonus: int, draw_date: Optional[str] = None):
        """당첨 데이터 추가 (API 동기화용)"""
        normalized = self._normalize_draw_input(draw_no, numbers, bonus)
        if not normalized:
            logger.warning(f"Invalid winning data ignored: draw_no={draw_no}")
            return

        parsed_draw_no, parsed_numbers, parsed_bonus = normalized

        if self.db_path:
            if self._save_to_db(parsed_draw_no, parsed_numbers, parsed_bonus, draw_date=draw_date):
                self._load_from_db()
                self._save()
                return

            if self._load_from_db():
                return

        # 중복 체크
        if any(d['draw_no'] == parsed_draw_no for d in self.winning_data):
            return
        
        self.winning_data.append({
            'draw_no': parsed_draw_no,
            'numbers': parsed_numbers,
            'bonus': parsed_bonus,
            'date': draw_date or datetime.datetime.now().isoformat()
        })
        
        # 회차순 정렬
        self.winning_data.sort(key=lambda x: x['draw_no'], reverse=True)
        
        # JSON 캐시 크기 제한 (DB가 없을 때만 적용)
        if not (self.db_path and self.db_path.exists()):
            cache_size = cast(int, APP_CONFIG['WINNING_STATS_CACHE_SIZE'])
            if len(self.winning_data) > cache_size:
                self.winning_data = self.winning_data[:cache_size]
        
        self._save()
    
    def reload_from_db(self):
        """DB에서 데이터 다시 로드 (수동 새로고침용)"""
        if self.db_path and self.db_path.exists():
            self._load_from_db()
    
    def get_frequency_analysis(self) -> Dict[str, Any]:
        """번호별 출현 빈도 분석"""
        if not self.winning_data:
            return {}
        
        # 번호별 출현 횟수
        number_counts = {i: 0 for i in range(1, 46)}
        bonus_counts = {i: 0 for i in range(1, 46)}
        
        for data in self.winning_data:
            for num in data['numbers']:
                if num in number_counts:
                    number_counts[num] += 1
            bonus = data.get('bonus')
            if bonus in bonus_counts:
                bonus_counts[bonus] += 1
        
        # 정렬
        sorted_by_count = sorted(number_counts.items(), key=lambda x: x[1], reverse=True)
        
        return {
            'total_draws': len(self.winning_data),
            'number_counts': number_counts,
            'bonus_counts': bonus_counts,
            'hot_numbers': sorted_by_count[:10],  # 핫 넘버 TOP 10
            'cold_numbers': sorted_by_count[-10:],  # 콜드 넘버 10개
        }
    
    def get_range_distribution(self) -> Dict[str, int]:
        """번호대별 분포 분석"""
        if not self.winning_data:
            return {}
        
        ranges = {'1-10': 0, '11-20': 0, '21-30': 0, '31-40': 0, '41-45': 0}
        
        for data in self.winning_data:
            for n in data['numbers']:
                if n <= 10: ranges['1-10'] += 1
                elif n <= 20: ranges['11-20'] += 1
                elif n <= 30: ranges['21-30'] += 1
                elif n <= 40: ranges['31-40'] += 1
                else: ranges['41-45'] += 1
        
        return ranges
    
    def get_pair_analysis(self) -> Dict[str, Any]:
        """연속 당첨 쌍 분석 (같이 나온 번호 쌍)"""
        if not self.winning_data:
            return {}
        
        pair_counts = {}
        
        for data in self.winning_data:
            nums = data['numbers']
            for i in range(len(nums)):
                for j in range(i + 1, len(nums)):
                    pair = (nums[i], nums[j])
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1
        
        # 가장 많이 나온 쌍 TOP 10
        sorted_pairs = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)
        return {'top_pairs': sorted_pairs[:10]}
    
    def get_recent_trend(self, count: int = 10) -> List[Dict[str, Any]]:
        """최근 N회차 트렌드"""
        return self.winning_data[:count]

