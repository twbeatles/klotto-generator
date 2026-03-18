from typing import Dict, List

from klotto.core.lotto_rules import calculate_rank, normalize_numbers

# ============================================================
# 번호 분석기
# ============================================================
class NumberAnalyzer:
    """생성된 번호 분석"""
    
    @staticmethod
    def analyze(numbers: List[int]) -> Dict:
        """번호 세트 분석"""
        normalized = normalize_numbers(numbers)
        if not normalized:
            return {}
        numbers = normalized
        
        total = sum(numbers)
        odd_count = sum(1 for n in numbers if n % 2 == 1)
        even_count = 6 - odd_count
        low_count = sum(1 for n in numbers if n <= 22)
        high_count = 6 - low_count
        
        # 번호대 분포
        ranges = {'1-10': 0, '11-20': 0, '21-30': 0, '31-40': 0, '41-45': 0}
        for n in numbers:
            if n <= 10: ranges['1-10'] += 1
            elif n <= 20: ranges['11-20'] += 1
            elif n <= 30: ranges['21-30'] += 1
            elif n <= 40: ranges['31-40'] += 1
            else: ranges['41-45'] += 1
        
        # 점수 계산 (적정 범위 기준)
        score = 100
        if total < 100 or total > 175:
            score -= 20
        if odd_count == 0 or even_count == 0:
            score -= 15
        if low_count == 0 or high_count == 0:
            score -= 15
        
        return {
            'total': total,
            'odd': odd_count,
            'even': even_count,
            'low': low_count,
            'high': high_count,
            'ranges': ranges,
            'score': max(0, score),
            'is_optimal': 100 <= total <= 175 and 2 <= odd_count <= 4
        }
    
    @staticmethod
    def compare_with_winning(numbers: List[int], winning: List[int], bonus: int) -> Dict:
        """당첨 번호와 비교"""
        normalized_numbers = normalize_numbers(numbers)
        normalized_winning = normalize_numbers(winning)
        if not normalized_numbers or not normalized_winning:
            return {}

        matched = set(normalized_numbers) & set(normalized_winning)
        bonus_matched = bonus in numbers
        match_count = len(matched)
        rank = calculate_rank(match_count, bonus_matched)

        return {
            'matched': list(matched),
            'match_count': match_count,
            'bonus_matched': bonus_matched,
            'rank': rank
        }
