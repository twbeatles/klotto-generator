import random
from typing import List, Optional, Set

from klotto.core.lotto_rules import validate_balance_constraints
from klotto.core.stats import WinningStatsManager


# ============================================================
# 통계 기반 스마트 번호 생성기
# ============================================================
class GenerationFailure(Exception):
    """번호 생성 시도 중 조건을 만족하지 못했을 때 발생하는 예외"""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


class SmartNumberGenerator:
    """통계 기반 스마트 번호 생성"""

    def __init__(self, stats_manager: WinningStatsManager):
        self.stats_manager = stats_manager

    def generate_smart_numbers(
        self,
        fixed_nums: Optional[Set[int]] = None,
        exclude_nums: Optional[Set[int]] = None,
        prefer_hot: bool = True,
        balance_mode: bool = True,
    ) -> List[int]:
        """스마트 번호 생성"""
        fixed_nums = fixed_nums or set()
        exclude_nums = exclude_nums or set()

        if balance_mode:
            balance_error = validate_balance_constraints(fixed_nums, exclude_nums)
            if balance_error:
                raise GenerationFailure("balance_constraints", balance_error)

        analysis = self.stats_manager.get_frequency_analysis()
        number_counts = analysis.get("number_counts", {}) if analysis else {}
        max_count = max(number_counts.values()) if number_counts.values() else 1

        candidates = []
        for num in range(1, 46):
            if num in fixed_nums or num in exclude_nums:
                continue

            count = number_counts.get(num, 0)
            weight = count + 1 if prefer_hot else max_count - count + 1
            candidates.append((num, weight))

        result = list(fixed_nums)

        while len(result) < 6 and candidates:
            current_candidates = candidates

            if balance_mode:
                valid_candidates = []
                remaining_slots = 6 - len(result)
                current_odd = sum(1 for n in result if n % 2 == 1)

                for num, weight in candidates:
                    is_odd = num % 2 == 1

                    if is_odd and current_odd >= 4:
                        continue

                    if not is_odd:
                        max_possible_odd = current_odd + (remaining_slots - 1)
                        if max_possible_odd < 2:
                            continue

                    valid_candidates.append((num, weight))

                current_candidates = valid_candidates

            if not current_candidates:
                raise GenerationFailure("candidate_exhausted", "조건을 만족하는 후보가 소진되었습니다.")

            total_weight = sum(weight for _, weight in current_candidates)
            if total_weight <= 0:
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
            candidates = [candidate for candidate in candidates if candidate[0] != selected_num]

        if len(result) < 6:
            raise GenerationFailure("candidate_exhausted", "조건을 만족하는 후보가 소진되었습니다.")

        return sorted(result)

    def generate_balanced_set(
        self,
        count: int = 5,
        fixed_nums: Optional[Set[int]] = None,
        exclude_nums: Optional[Set[int]] = None,
    ) -> List[List[int]]:
        """균형 잡힌 세트 생성 (다양한 전략 조합)"""
        results = []
        strategies = [
            {"prefer_hot": True, "balance_mode": True},
            {"prefer_hot": False, "balance_mode": True},
            {"prefer_hot": True, "balance_mode": False},
        ]

        for i in range(count):
            strategy = strategies[i % len(strategies)]
            nums = self.generate_smart_numbers(
                fixed_nums=fixed_nums,
                exclude_nums=exclude_nums,
                **strategy,
            )
            results.append(nums)

        return results
