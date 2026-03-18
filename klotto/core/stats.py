import json
import datetime
import os
import sqlite3
from pathlib import Path
from typing import Any, List, Dict, Optional, Tuple, cast
from klotto.config import APP_CONFIG
from klotto.core.lotto_rules import normalize_bonus, normalize_numbers, normalize_positive_int
from klotto.logging import logger

# ============================================================
# 역대 당첨 번호 통계 관리
# ============================================================
class WinningStatsManager:
    """역대 당첨 번호 통계 관리 (SQLite DB 우선, JSON 폴백)"""
    
    def __init__(self):
        self.stats_file: Path = cast(Path, APP_CONFIG['WINNING_STATS_FILE'])
        self.db_path: Path = cast(Path, APP_CONFIG['LOTTO_HISTORY_DB'])
        self.winning_data: List[Dict[str, Any]] = []
        self._draw_index: Dict[int, Dict[str, Any]] = {}
        self._frequency_cache: Optional[Dict[str, Any]] = None
        self._range_cache: Optional[Dict[str, int]] = None
        self._pair_cache: Optional[Dict[str, Any]] = None
        self._load()

    def _invalidate_analysis_cache(self):
        self._frequency_cache = None
        self._range_cache = None
        self._pair_cache = None

    def _set_winning_data(self, data: List[Dict[str, Any]]):
        self.winning_data = data
        self._draw_index = {}
        for row in data:
            if not isinstance(row, dict):
                continue
            try:
                raw_draw_no = row.get('draw_no')
                if raw_draw_no is None:
                    continue
                draw_no = int(raw_draw_no)
            except (TypeError, ValueError):
                continue
            self._draw_index[draw_no] = row
        self._invalidate_analysis_cache()

    def _append_draw_data(self, draw_no: int, numbers: List[int], bonus: int, draw_date: Optional[str] = None):
        row = {
            'draw_no': draw_no,
            'numbers': numbers,
            'bonus': bonus,
            'date': draw_date or datetime.datetime.now().isoformat()
        }
        self.winning_data.append(row)
        self.winning_data.sort(key=lambda x: x['draw_no'], reverse=True)
        self._draw_index[draw_no] = row
        self._invalidate_analysis_cache()
    
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
            
            parsed_data: List[Dict[str, Any]] = []
            invalid_count = 0
            for row in rows:
                normalized = self._normalize_draw_input(row[0], [row[2], row[3], row[4], row[5], row[6], row[7]], row[8])
                if not normalized:
                    invalid_count += 1
                    continue

                draw_no, numbers, bonus = normalized
                parsed_data.append({
                    'draw_no': draw_no,
                    'date': row[1] or '',
                    'numbers': numbers,
                    'bonus': bonus
                })

            if invalid_count:
                logger.warning(f"Skipped {invalid_count} invalid winning records from DB")

            if not parsed_data:
                return False

            self._set_winning_data(parsed_data)
            
            logger.info(f"Loaded {len(self.winning_data)} winning records from DB")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load from DB: {e}")
            return False

    def _normalize_draw_input(self, draw_no: Any, numbers: List[Any], bonus: Any) -> Optional[Tuple[int, List[int], int]]:
        """입력 당첨 데이터 정규화 및 검증"""
        parsed_draw_no = normalize_positive_int(draw_no)
        parsed_numbers = normalize_numbers(numbers)
        if parsed_draw_no is None or parsed_numbers is None:
            return None
        parsed_bonus = normalize_bonus(bonus, parsed_numbers)
        if parsed_bonus is None:
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
                    loaded = json.load(f)

                parsed_data: List[Dict[str, Any]] = []
                seen_draws = set()
                for item in loaded if isinstance(loaded, list) else []:
                    if not isinstance(item, dict):
                        continue

                    normalized = self._normalize_draw_input(
                        item.get('draw_no'),
                        item.get('numbers', []),
                        item.get('bonus'),
                    )
                    if not normalized:
                        continue

                    draw_no, numbers, bonus = normalized
                    if draw_no in seen_draws:
                        continue

                    date_value = item.get('date')
                    parsed_data.append({
                        'draw_no': draw_no,
                        'numbers': numbers,
                        'bonus': bonus,
                        'date': date_value if isinstance(date_value, str) else ''
                    })
                    seen_draws.add(draw_no)

                parsed_data.sort(key=lambda x: x['draw_no'], reverse=True)
                self._set_winning_data(parsed_data)
                logger.info(f"Loaded {len(self.winning_data)} winning records from JSON")
            else:
                self._set_winning_data([])
        except Exception as e:
            logger.error(f"Failed to load winning stats: {e}")
            self._set_winning_data([])
    
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
    
    def add_winning_data(self, draw_no: int, numbers: List[int], bonus: int, draw_date: Optional[str] = None) -> bool:
        """당첨 데이터 추가 (신규 저장 시 True, 중복/실패 시 False)"""
        normalized = self._normalize_draw_input(draw_no, numbers, bonus)
        if not normalized:
            logger.warning(f"Invalid winning data ignored: draw_no={draw_no}")
            return False

        parsed_draw_no, parsed_numbers, parsed_bonus = normalized

        # 메모리 캐시 중복 체크 (O(1))
        if parsed_draw_no in self._draw_index:
            return False

        if self.db_path:
            if self._save_to_db(parsed_draw_no, parsed_numbers, parsed_bonus, draw_date=draw_date):
                self._append_draw_data(parsed_draw_no, parsed_numbers, parsed_bonus, draw_date=draw_date)
                self._save()
                return True

            # DB 삽입 실패 시 최신 상태 다시 로드 (중복 여부 동기화)
            if self._load_from_db():
                return False

        if parsed_draw_no in self._draw_index:
            return False
        
        self._append_draw_data(parsed_draw_no, parsed_numbers, parsed_bonus, draw_date=draw_date)
        
        # JSON 캐시 크기 제한 (DB가 없을 때만 적용)
        if not (self.db_path and self.db_path.exists()):
            cache_size = cast(int, APP_CONFIG['WINNING_STATS_CACHE_SIZE'])
            if len(self.winning_data) > cache_size:
                self._set_winning_data(self.winning_data[:cache_size])
        
        self._save()
        return True

    def get_draw_data(self, draw_no: int) -> Optional[Dict[str, Any]]:
        """특정 회차 데이터 반환"""
        try:
            target = int(draw_no)
        except (TypeError, ValueError):
            return None

        if target <= 0:
            return None

        cached = self._draw_index.get(target)
        if cached:
            return cached

        # 캐시가 오래됐을 수 있으므로 DB 재로드 후 한 번 더 조회
        if self.db_path and self.db_path.exists():
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        '''
                        SELECT draw_no, date, num1, num2, num3, num4, num5, num6, bonus
                        FROM draws
                        WHERE draw_no = ?
                        LIMIT 1
                        ''',
                        (target,),
                    )
                    row = cursor.fetchone()
                if row:
                    normalized = self._normalize_draw_input(row[0], [row[2], row[3], row[4], row[5], row[6], row[7]], row[8])
                    if normalized:
                        parsed_draw_no, numbers, bonus = normalized
                        self._append_draw_data(parsed_draw_no, numbers, bonus, draw_date=row[1] or '')
                        return self._draw_index.get(parsed_draw_no)
            except Exception as e:
                logger.error(f"Failed to query draw #{target} from DB: {e}")

        return None
    
    def reload_from_db(self):
        """DB에서 데이터 다시 로드 (수동 새로고침용)"""
        if self.db_path and self.db_path.exists():
            self._load_from_db()
    
    def get_frequency_analysis(self) -> Dict[str, Any]:
        """번호별 출현 빈도 분석"""
        if self._frequency_cache is not None:
            return dict(self._frequency_cache)

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
        
        self._frequency_cache = {
            'total_draws': len(self.winning_data),
            'number_counts': number_counts,
            'bonus_counts': bonus_counts,
            'hot_numbers': sorted_by_count[:10],  # 핫 넘버 TOP 10
            'cold_numbers': sorted_by_count[-10:],  # 콜드 넘버 10개
        }
        return dict(self._frequency_cache)
    
    def get_range_distribution(self) -> Dict[str, int]:
        """번호대별 분포 분석"""
        if self._range_cache is not None:
            return dict(self._range_cache)

        if not self.winning_data:
            return {}

        frequency = self.get_frequency_analysis()
        number_counts = frequency.get('number_counts', {})
        if not isinstance(number_counts, dict):
            return {}

        ranges = {
            '1-10': sum(number_counts.get(i, 0) for i in range(1, 11)),
            '11-20': sum(number_counts.get(i, 0) for i in range(11, 21)),
            '21-30': sum(number_counts.get(i, 0) for i in range(21, 31)),
            '31-40': sum(number_counts.get(i, 0) for i in range(31, 41)),
            '41-45': sum(number_counts.get(i, 0) for i in range(41, 46)),
        }
        self._range_cache = ranges
        return dict(ranges)
    
    def get_pair_analysis(self) -> Dict[str, Any]:
        """연속 당첨 쌍 분석 (같이 나온 번호 쌍)"""
        if self._pair_cache is not None:
            return dict(self._pair_cache)

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
        self._pair_cache = {'top_pairs': sorted_pairs[:10]}
        return dict(self._pair_cache)
    
    def get_recent_trend(self, count: int = 10) -> List[Dict[str, Any]]:
        """최근 N회차 트렌드"""
        return self.winning_data[:count]

