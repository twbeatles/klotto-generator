from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from klotto.core.lotto_rules import count_consecutive_pairs


class AdvancedMonteCarlo:
    @staticmethod
    def weighted_sample(weights: Sequence[float], k: int = 6, rng: Callable[[], float] | None = None) -> List[int]:
        random_fn = rng or __import__('random').random
        chosen: set[int] = set()
        safe_weights = list(weights) if len(weights) >= 46 else ([1.0] * 46)
        safety = 0
        while len(chosen) < k and safety < 200:
            safety += 1
            total = 0.0
            for number in range(1, 46):
                if number not in chosen:
                    total += max(0.0001, float(safe_weights[number] if number < len(safe_weights) else 1.0))
            threshold = random_fn() * total
            for number in range(1, 46):
                if number in chosen:
                    continue
                threshold -= max(0.0001, float(safe_weights[number] if number < len(safe_weights) else 1.0))
                if threshold <= 0:
                    chosen.add(number)
                    break
        if len(chosen) < k:
            for number in range(1, 46):
                chosen.add(number)
                if len(chosen) >= k:
                    break
        return sorted(chosen)

    @staticmethod
    def calculate_sum(numbers: Iterable[int]) -> int:
        return sum(int(number) for number in numbers)

    @staticmethod
    def calculate_ac(numbers: Sequence[int]) -> int:
        if len(numbers) < 6:
            return 0
        diffs = {abs(int(numbers[j]) - int(numbers[i])) for i in range(len(numbers)) for j in range(i + 1, len(numbers))}
        return len(diffs) - 5


FilterDict = Dict[str, Any]


def _normalize_int(value: Any, min_value: int, max_value: int) -> Optional[int]:
    if value in (None, '', []):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(min_value, min(max_value, parsed))



def _normalize_pair(value: Any) -> Optional[List[int]]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        first = int(value[0])
        second = int(value[1])
    except (TypeError, ValueError):
        return None
    return [first, second] if first <= second else [second, first]



def sanitize_filters(filters: FilterDict | None = None) -> FilterDict:
    raw = filters or {}
    return {
        'oddEven': _normalize_pair(raw.get('oddEven')),
        'highLow': _normalize_pair(raw.get('highLow')),
        'sumRange': _normalize_pair(raw.get('sumRange')),
        'acRange': _normalize_pair(raw.get('acRange')),
        'maxConsecutivePairs': _normalize_int(raw.get('maxConsecutivePairs'), 0, 5),
        'endDigitUniqueMin': _normalize_int(raw.get('endDigitUniqueMin'), 1, 6),
    }



def _to_sorted_unique_numbers(numbers: Sequence[int], *, assume_sorted: bool = False) -> Optional[List[int]]:
    if len(numbers) != 6:
        return None
    sorted_numbers = list(numbers) if assume_sorted else sorted(int(number) for number in numbers)
    for index, value in enumerate(sorted_numbers):
        if not isinstance(value, int):
            value = int(value)
            sorted_numbers[index] = value
        if value < 1 or value > 45:
            return None
        if index > 0 and value == sorted_numbers[index - 1]:
            return None
    return sorted_numbers



def create_filter_evaluator(filters: FilterDict | None = None) -> Callable[[Sequence[int], bool], bool]:
    sanitized = sanitize_filters(filters)

    def evaluate(numbers: Sequence[int], assume_sorted: bool = False) -> bool:
        sorted_numbers = _to_sorted_unique_numbers(numbers, assume_sorted=assume_sorted)
        if not sorted_numbers:
            return False

        odd = sum(1 for number in sorted_numbers if number % 2)
        high = sum(1 for number in sorted_numbers if number > 23)
        total = sum(sorted_numbers)
        consecutive_pairs = count_consecutive_pairs(sorted_numbers)
        end_digits = {number % 10 for number in sorted_numbers}

        odd_even = sanitized.get('oddEven')
        if odd_even and not (odd_even[0] <= odd <= odd_even[1]):
            return False

        high_low = sanitized.get('highLow')
        if high_low and not (high_low[0] <= high <= high_low[1]):
            return False

        sum_range = sanitized.get('sumRange')
        if sum_range and not (sum_range[0] <= total <= sum_range[1]):
            return False

        max_consecutive = sanitized.get('maxConsecutivePairs')
        if max_consecutive is not None and consecutive_pairs > max_consecutive:
            return False

        end_digit_unique_min = sanitized.get('endDigitUniqueMin')
        if end_digit_unique_min is not None and len(end_digits) < end_digit_unique_min:
            return False

        ac_range = sanitized.get('acRange')
        if ac_range:
            ac = AdvancedMonteCarlo.calculate_ac(sorted_numbers)
            if not (ac_range[0] <= ac <= ac_range[1]):
                return False

        return True

    return evaluate



def passes_filters(numbers: Sequence[int], filters: FilterDict | None = None) -> bool:
    return create_filter_evaluator(filters)(numbers, False)


__all__ = [
    'AdvancedMonteCarlo',
    'create_filter_evaluator',
    'passes_filters',
    'sanitize_filters',
]
