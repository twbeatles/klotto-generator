import json
import datetime
import os
from typing import List, Dict
from klotto.config import APP_CONFIG
from klotto.utils import logger

# ============================================================
# 역대 당첨 번호 통계 관리
# ============================================================
class WinningStatsManager:
    """역대 당첨 번호 통계 관리"""
    
    def __init__(self):
        self.stats_file = APP_CONFIG['WINNING_STATS_FILE']
        self.winning_data: List[Dict] = []
        self._load()
    
    def _load(self):
        """파일에서 통계 데이터 로드"""
        try:
            if self.stats_file and self.stats_file.exists():
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    self.winning_data = json.load(f)
                logger.info(f"Loaded {len(self.winning_data)} winning records")
        except Exception as e:
            logger.error(f"Failed to load winning stats: {e}")
            self.winning_data = []
    
    def _save(self):
        """통계 데이터 저장 (Atomic)"""
        if not self.stats_file:
            return

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
                if 'temp_file' in locals() and temp_file.exists():
                    temp_file.unlink()
            except: pass
    
    def add_winning_data(self, draw_no: int, numbers: List[int], bonus: int):
        """당첨 데이터 추가"""
        # 중복 체크
        if any(d['draw_no'] == draw_no for d in self.winning_data):
            return
        
        self.winning_data.append({
            'draw_no': draw_no,
            'numbers': sorted(numbers),
            'bonus': bonus,
            'date': datetime.datetime.now().isoformat()
        })
        
        # 회차순 정렬
        self.winning_data.sort(key=lambda x: x['draw_no'], reverse=True)
        
        # 캐시 크기 제한
        if len(self.winning_data) > APP_CONFIG['WINNING_STATS_CACHE_SIZE']:
            self.winning_data = self.winning_data[:APP_CONFIG['WINNING_STATS_CACHE_SIZE']]
        
        self._save()
    
    def get_frequency_analysis(self) -> Dict:
        """번호별 출현 빈도 분석"""
        if not self.winning_data:
            return {}
        
        # 번호별 출현 횟수
        number_counts = {i: 0 for i in range(1, 46)}
        bonus_counts = {i: 0 for i in range(1, 46)}
        
        for data in self.winning_data:
            for num in data['numbers']:
                number_counts[num] += 1
            bonus_counts[data['bonus']] += 1
        
        # 정렬
        sorted_by_count = sorted(number_counts.items(), key=lambda x: x[1], reverse=True)
        
        return {
            'total_draws': len(self.winning_data),
            'number_counts': number_counts,
            'bonus_counts': bonus_counts,
            'hot_numbers': sorted_by_count[:10],  # 핫 넘버 TOP 10
            'cold_numbers': sorted_by_count[-10:],  # 콜드 넘버 10개
        }
    
    def get_range_distribution(self) -> Dict:
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
    
    def get_pair_analysis(self) -> Dict:
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
    
    def get_recent_trend(self, count: int = 10) -> List[Dict]:
        """최근 N회차 트렌드"""
        return self.winning_data[:count]
