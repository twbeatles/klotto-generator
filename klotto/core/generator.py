import random
from typing import List, Set, Dict
from klotto.core.stats import WinningStatsManager

# ============================================================
# 통계 기반 스마트 번호 생성기
# ============================================================
class SmartNumberGenerator:
    """통계 기반 스마트 번호 생성"""
    
    def __init__(self, stats_manager: WinningStatsManager):
        self.stats_manager = stats_manager
    
    def generate_smart_numbers(self, fixed_nums: Set[int] = None, 
                                exclude_nums: Set[int] = None,
                                prefer_hot: bool = True,
                                balance_mode: bool = True) -> List[int]:
        """스마트 번호 생성"""
        fixed_nums = fixed_nums or set()
        exclude_nums = exclude_nums or set()
        
        # 통계 데이터 가져오기
        analysis = self.stats_manager.get_frequency_analysis()
        
        if not analysis:
            # 통계 데이터 없으면 일반 랜덤 생성
            available = set(range(1, 46)) - fixed_nums - exclude_nums
            remaining = 6 - len(fixed_nums)
            return sorted(list(fixed_nums) + random.sample(list(available), remaining))
        
        number_counts = analysis['number_counts']
        max_count = max(number_counts.values()) if number_counts.values() else 1
        
        # 초기 후보군 생성 (가중치 계산)
        candidates = []
        for num in range(1, 46):
            if num in fixed_nums or num in exclude_nums:
                continue
            
            count = number_counts.get(num, 0)
            if prefer_hot:
                weight = count + 1
            else:
                weight = max_count - count + 1
            candidates.append((num, weight))
        
        result = list(fixed_nums)
        
        # 번호 선택 루프
        while len(result) < 6 and candidates:
            # 균형 모드일 경우 유효한 후보 필터링
            current_candidates = candidates
            
            if balance_mode:
                valid_candidates = []
                remaining_slots = 6 - len(result)
                current_odd = sum(1 for n in result if n % 2 == 1)
                
                for num, weight in candidates:
                    is_odd = (num % 2 == 1)
                    
                    # 1. 홀수 과다 방지: 홀수가 이미 4개면 홀수 선택 불가
                    if is_odd and current_odd >= 4:
                        continue
                        
                    # 2. 짝수 과다 방지: (홀수 부족 방지)
                    # 짝수를 골랐을 때, 남은 자리를 모두 홀수로 채워도 최소 홀수(2개)를 만족 못하면 안됨
                    # 즉: 현재홀수 + (남은자리-1) < 2 이면 짝수 선택 불가
                    if not is_odd:
                        max_possible_odd = current_odd + (remaining_slots - 1)
                        if max_possible_odd < 2:
                            continue
                            
                    valid_candidates.append((num, weight))
                
                current_candidates = valid_candidates
                
            if not current_candidates:
                break
                
            # 가중치 기반 확률 선택
            total_weight = sum(w for n, w in current_candidates)
            if total_weight <= 0:
                # 비상시 (혹은 실수로) 랜덤 선택
                selected_tuple = random.choice(current_candidates)
            else:
                r = random.uniform(0, total_weight)
                cumulative = 0
                selected_tuple = None
                
                for item in current_candidates:
                    cumulative += item[1]
                    if cumulative >= r:
                        selected_tuple = item
                        break
                
                if not selected_tuple:
                    selected_tuple = current_candidates[-1]
            
            selected_num = selected_tuple[0]
            result.append(selected_num)
            
            # 선택된 번호 제거 (원본 후보군에서)
            candidates = [c for c in candidates if c[0] != selected_num]
        
        return sorted(result)
    
    def generate_balanced_set(self, count: int = 5, 
                               fixed_nums: Set[int] = None,
                               exclude_nums: Set[int] = None) -> List[List[int]]:
        """균형 잡힌 세트 생성 (다양한 전략 조합)"""
        results = []
        strategies = [
            {'prefer_hot': True, 'balance_mode': True},   # 핫넘버 + 균형
            {'prefer_hot': False, 'balance_mode': True},  # 콜드넘버 + 균형
            {'prefer_hot': True, 'balance_mode': False},  # 핫넘버만
        ]
        
        for i in range(count):
            strategy = strategies[i % len(strategies)]
            nums = self.generate_smart_numbers(
                fixed_nums=fixed_nums,
                exclude_nums=exclude_nums,
                **strategy
            )
            results.append(nums)
        
        return results
