import json
import datetime
import os
from typing import List, Dict, Optional, Tuple, Set
from klotto.config import APP_CONFIG
from klotto.utils import logger

# ============================================================
# 히스토리 관리
# ============================================================
class HistoryManager:
    """생성된 번호 히스토리 관리"""
    
    def __init__(self):
        self.history_file = APP_CONFIG['HISTORY_FILE']
        self.history: List[Dict] = []
        self._history_keys: Set[Tuple[int, ...]] = set()
        self._stats_cache: Optional[Dict] = None
        self._load()

    @staticmethod
    def _numbers_to_key(numbers: List[int], validate: bool = False) -> Optional[Tuple[int, ...]]:
        try:
            normalized = tuple(sorted(int(n) for n in numbers))
        except (TypeError, ValueError):
            return None

        if not validate:
            return normalized

        if len(normalized) != 6 or len(set(normalized)) != 6:
            return None
        if any(n < 1 or n > 45 for n in normalized):
            return None
        return normalized

    def _rebuild_index(self):
        normalized_history: List[Dict] = []
        self._history_keys.clear()

        for entry in self.history:
            if not isinstance(entry, dict):
                continue

            key = self._numbers_to_key(entry.get('numbers', []), validate=True)
            if not key or key in self._history_keys:
                continue

            created_at = entry.get('created_at')
            if not isinstance(created_at, str):
                created_at = datetime.datetime.now().isoformat()

            normalized_history.append({
                'numbers': list(key),
                'created_at': created_at
            })
            self._history_keys.add(key)

        self.history = normalized_history
        self._trim_to_max()
        self._stats_cache = None

    def _trim_to_max(self):
        max_history = APP_CONFIG['MAX_HISTORY']
        while len(self.history) > max_history:
            removed = self.history.pop()
            key = self._numbers_to_key(removed.get('numbers', []))
            if key:
                self._history_keys.discard(key)
    
    def _load(self):
        """파일에서 히스토리 로드"""
        try:
            if self.history_file and self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
                logger.info(f"Loaded {len(self.history)} history entries")
        except Exception as e:
            logger.error(f"Failed to load history: {e}")
            self.history = []
        finally:
            self._rebuild_index()
    
    def _save(self):
        """히스토리를 파일에 저장 (Atomic)"""
        if not self.history_file:
            return

        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file = self.history_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
                
            if self.history_file.exists():
                os.replace(temp_file, self.history_file)
            else:
                os.rename(temp_file, self.history_file)
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
            try:
                if 'temp_file' in locals() and temp_file.exists():
                    temp_file.unlink()
            except: pass
    
    def add(self, numbers: List[int], save: bool = True) -> bool:
        """히스토리에 추가 (중복 체크)"""
        key = self._numbers_to_key(numbers, validate=True)
        if not key:
            return False

        if key in self._history_keys:
            return False

            self.history.insert(0, {
                'numbers': list(key),
                'created_at': datetime.datetime.now().isoformat()
            })
            self._history_keys.add(key)
            self._trim_to_max()
            self._stats_cache = None

        if save:
            self._save()
        return True

    def add_many(self, numbers_sets: List[List[int]]) -> List[List[int]]:
        """히스토리에 여러 조합 추가 (단일 파일 저장)"""
        added_sets: List[List[int]] = []
        changed = False

        for numbers in numbers_sets:
            if self.add(numbers, save=False):
                key = self._numbers_to_key(numbers)
                if key:
                    added_sets.append(list(key))
                changed = True

        if changed:
            self._save()
            self._stats_cache = None

        return added_sets
    
    def is_duplicate(self, numbers: List[int]) -> bool:
        """중복 조합인지 확인"""
        key = self._numbers_to_key(numbers)
        if not key:
            return False
        return key in self._history_keys

    def get_number_keys(self) -> Set[Tuple[int, ...]]:
        """중복 확인용 번호 키 집합 반환"""
        return set(self._history_keys)
    
    def get_all(self) -> List[Dict]:
        return self.history.copy()
    
    def get_recent(self, count: int = 50) -> List[Dict]:
        """최근 N개 히스토리"""
        return self.history[:count]
    
    def clear(self):
        """히스토리 전체 삭제"""
        self.history = []
        self._history_keys.clear()
        self._stats_cache = None
        self._save()
    
    def get_statistics(self) -> Dict:
        """히스토리 기반 통계"""
        if self._stats_cache is not None:
            return dict(self._stats_cache)

        if not self.history:
            return {}
        
        # 번호별 출현 횟수
        number_counts = {i: 0 for i in range(1, 46)}
        for h in self.history:
            for num in h['numbers']:
                number_counts[num] += 1
        
        # 정렬
        sorted_by_count = sorted(number_counts.items(), key=lambda x: x[1], reverse=True)
        
        self._stats_cache = {
            'total_sets': len(self.history),
            'number_counts': number_counts,
            'most_common': sorted_by_count[:10],
            'least_common': sorted_by_count[-10:]
        }
        return dict(self._stats_cache)
