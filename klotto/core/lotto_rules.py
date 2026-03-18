from typing import Any, Iterable, List, Optional, Sequence, Set


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_positive_int(value: Any) -> Optional[int]:
    parsed = safe_int(value, default=0)
    return parsed if parsed > 0 else None


def normalize_numbers(value: Any) -> Optional[List[int]]:
    if not isinstance(value, (list, tuple, set)):
        return None

    try:
        numbers = sorted(int(item) for item in value)
    except (TypeError, ValueError):
        return None

    if len(numbers) != 6 or len(set(numbers)) != 6:
        return None
    if any(number < 1 or number > 45 for number in numbers):
        return None
    return numbers


def normalize_bonus(value: Any, numbers: Sequence[int]) -> Optional[int]:
    bonus = normalize_positive_int(value)
    if bonus is None:
        return None
    if bonus < 1 or bonus > 45 or bonus in numbers:
        return None
    return bonus


def parse_number_expression(text: str, field_name: str = "번호") -> Set[int]:
    parsed: Set[int] = set()
    raw = (text or "").strip()
    if not raw:
        return parsed

    for token in raw.split(","):
        item = token.strip()
        if not item:
            continue

        if "-" in item:
            parts = item.split("-")
            if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
                raise ValueError(f"{field_name} 형식 오류: '{item}'")
            try:
                start = int(parts[0].strip())
                end = int(parts[1].strip())
            except ValueError as exc:
                raise ValueError(f"{field_name}에 숫자가 아닌 값이 있습니다: '{item}'") from exc

            if start > end:
                raise ValueError(f"{field_name} 범위는 시작값이 끝값보다 클 수 없습니다: '{item}'")
            if start < 1 or end > 45:
                raise ValueError(f"{field_name}는 1~45 범위만 허용됩니다: '{item}'")
            parsed.update(range(start, end + 1))
            continue

        try:
            number = int(item)
        except ValueError as exc:
            raise ValueError(f"{field_name}에 숫자가 아닌 값이 있습니다: '{item}'") from exc

        if number < 1 or number > 45:
            raise ValueError(f"{field_name}는 1~45 범위만 허용됩니다: '{item}'")
        parsed.add(number)

    return parsed


def validate_generation_constraints(
    fixed_nums: Iterable[int],
    exclude_nums: Iterable[int],
    *,
    max_fixed_nums: int = 6,
) -> Optional[str]:
    fixed_set = set(fixed_nums)
    exclude_set = set(exclude_nums)

    if len(fixed_set) > max_fixed_nums:
        return f"고정수는 최대 {max_fixed_nums}개까지 지정할 수 있습니다."

    overlap = fixed_set & exclude_set
    if overlap:
        conflict = ", ".join(str(number) for number in sorted(overlap))
        return f"고정수와 제외수가 겹칩니다: {conflict}"

    available = set(range(1, 46)) - fixed_set - exclude_set
    required = 6 - len(fixed_set)
    if len(available) < required:
        return "고정수/제외수 조건으로는 6개 번호를 만들 수 없습니다."

    return None


def validate_balance_constraints(
    fixed_nums: Iterable[int],
    exclude_nums: Iterable[int],
    *,
    total_numbers: int = 6,
    min_odd_count: int = 2,
    max_odd_count: int = 4,
) -> Optional[str]:
    fixed_set = set(fixed_nums)
    exclude_set = set(exclude_nums)
    available = set(range(1, 46)) - fixed_set - exclude_set
    required = total_numbers - len(fixed_set)

    if required < 0:
        return "고정수 개수가 전체 번호 개수를 초과했습니다."

    fixed_odd_count = sum(1 for number in fixed_set if number % 2 == 1)
    available_odd_count = sum(1 for number in available if number % 2 == 1)
    available_even_count = len(available) - available_odd_count

    min_possible_odd = fixed_odd_count + max(0, required - available_even_count)
    max_possible_odd = fixed_odd_count + min(required, available_odd_count)

    if min_possible_odd > max_odd_count or max_possible_odd < min_odd_count:
        return "현재 고정수/제외수 조건으로는 홀짝 균형(홀수 2~4개)을 만족할 수 없습니다."

    return None


def count_consecutive_pairs(numbers: Sequence[int]) -> int:
    return sum(1 for index in range(len(numbers) - 1) if numbers[index + 1] == numbers[index] + 1)


def calculate_rank(match_count: int, bonus_matched: bool) -> Optional[int]:
    if match_count == 6:
        return 1
    if match_count == 5 and bonus_matched:
        return 2
    if match_count == 5:
        return 3
    if match_count == 4:
        return 4
    if match_count == 3:
        return 5
    return None


__all__ = [
    "calculate_rank",
    "count_consecutive_pairs",
    "normalize_bonus",
    "normalize_numbers",
    "normalize_positive_int",
    "parse_number_expression",
    "safe_int",
    "validate_balance_constraints",
    "validate_generation_constraints",
]
