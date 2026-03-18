import random
from dataclasses import dataclass, field
from typing import List, Set, Tuple

from klotto.core.generator import SmartNumberGenerator
from klotto.core.lotto_rules import count_consecutive_pairs, validate_generation_constraints
from klotto.data.history import HistoryManager


@dataclass(frozen=True)
class GenerationRequest:
    count: int
    use_smart: bool
    prefer_hot: bool
    balance_mode: bool
    limit_consecutive: bool
    fixed_nums: Set[int] = field(default_factory=set)
    exclude_nums: Set[int] = field(default_factory=set)
    max_generate_retries: int = 100


@dataclass(frozen=True)
class GenerationResult:
    requested_count: int
    generated_sets: List[List[int]]
    failed_count: int


class GenerationService:
    def __init__(self, history_manager: HistoryManager, smart_generator: SmartNumberGenerator):
        self.history_manager = history_manager
        self.smart_generator = smart_generator

    def generate_batch(self, request: GenerationRequest) -> GenerationResult:
        validation_error = validate_generation_constraints(request.fixed_nums, request.exclude_nums)
        if validation_error:
            raise ValueError(validation_error)

        generated_sets: List[List[int]] = []
        failed_count = 0
        existing_keys = self.history_manager.get_number_keys()
        generated_keys: Set[Tuple[int, ...]] = set()

        for _ in range(request.count):
            numbers: List[int] = []
            valid = False

            for _ in range(request.max_generate_retries):
                if request.use_smart:
                    numbers = self.smart_generator.generate_smart_numbers(
                        fixed_nums=request.fixed_nums,
                        exclude_nums=request.exclude_nums,
                        prefer_hot=request.prefer_hot,
                        balance_mode=request.balance_mode,
                    )
                else:
                    available = set(range(1, 46)) - request.fixed_nums - request.exclude_nums
                    remaining = 6 - len(request.fixed_nums)
                    numbers = sorted(list(request.fixed_nums) + random.sample(list(available), remaining))

                valid = True
                if request.limit_consecutive and count_consecutive_pairs(numbers) > 2:
                    valid = False

                key = tuple(numbers)
                if key in existing_keys or key in generated_keys:
                    valid = False

                if valid:
                    break

            if not valid:
                failed_count += 1
                continue

            key = tuple(numbers)
            generated_keys.add(key)
            generated_sets.append(numbers)

        result_sets = self.history_manager.add_many(generated_sets)
        failed_count += max(0, len(generated_sets) - len(result_sets))

        return GenerationResult(
            requested_count=request.count,
            generated_sets=result_sets,
            failed_count=failed_count,
        )


__all__ = ["GenerationRequest", "GenerationResult", "GenerationService"]
