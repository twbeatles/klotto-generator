import json
import datetime
import os
from typing import List, Dict
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
        self._load()
    
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
    
    def add(self, numbers: List[int]) -> bool:
        """히스토리에 추가 (중복 체크)"""
        sorted_nums = sorted(numbers)
        
        # 중복 체크
        for h in self.history:
            if h['numbers'] == sorted_nums:
                return False  # 이미 생성된 조합
        
        self.history.insert(0, {
            'numbers': sorted_nums,
            'created_at': datetime.datetime.now().isoformat()
        })
        
        # 최대 개수 제한
        if len(self.history) > APP_CONFIG['MAX_HISTORY']:
            self.history = self.history[:APP_CONFIG['MAX_HISTORY']]
        
        self._save()
        return True
    
    def is_duplicate(self, numbers: List[int]) -> bool:
        """중복 조합인지 확인"""
        sorted_nums = sorted(numbers)
        return any(h['numbers'] == sorted_nums for h in self.history)
    
    def get_all(self) -> List[Dict]:
        return self.history.copy()
    
    def get_recent(self, count: int = 50) -> List[Dict]:
        """최근 N개 히스토리"""
        return self.history[:count]
    
    def clear(self):
        """히스토리 전체 삭제"""
        self.history = []
        self._save()
    
    def get_statistics(self) -> Dict:
        """히스토리 기반 통계"""
        if not self.history:
            return {}
        
        # 번호별 출현 횟수
        number_counts = {i: 0 for i in range(1, 46)}
        for h in self.history:
            for num in h['numbers']:
                number_counts[num] += 1
        
        # 정렬
        sorted_by_count = sorted(number_counts.items(), key=lambda x: x[1], reverse=True)
        
        return {
            'total_sets': len(self.history),
            'number_counts': number_counts,
            'most_common': sorted_by_count[:10],
            'least_common': sorted_by_count[-10:]
        }
