import random
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from klotto.core.generator import GenerationFailure, SmartNumberGenerator
from klotto.core.lotto_rules import (
    count_consecutive_pairs,
    validate_balance_constraints,
    validate_generation_constraints,
)
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
    failure_reasons: Dict[str, int]


class GenerationService:
    FAILURE_KEYS = (
        "balance_constraints",
        "consecutive_limit",
        "duplicate_history",
        "duplicate_batch",
        "candidate_exhausted",
    )

    def __init__(self, history_manager: HistoryManager, smart_generator: SmartNumberGenerator):
        self.history_manager = history_manager
        self.smart_generator = smart_generator

    def generate_batch(self, request: GenerationRequest) -> GenerationResult:
        validation_error = validate_generation_constraints(request.fixed_nums, request.exclude_nums)
        if validation_error:
            raise ValueError(validation_error)

        if request.use_smart and request.balance_mode:
            balance_error = validate_balance_constraints(request.fixed_nums, request.exclude_nums)
            if balance_error:
                raise ValueError(balance_error)

        generated_sets: List[List[int]] = []
        failed_count = 0
        existing_keys = self.history_manager.get_number_keys()
        generated_keys: Set[Tuple[int, ...]] = set()
        failure_reasons = {key: 0 for key in self.FAILURE_KEYS}

        for _ in range(request.count):
            numbers: List[int] = []
            valid = False

            for _ in range(request.max_generate_retries):
                if request.use_smart:
                    try:
                        numbers = self.smart_generator.generate_smart_numbers(
                            fixed_nums=request.fixed_nums,
                            exclude_nums=request.exclude_nums,
                            prefer_hot=request.prefer_hot,
                            balance_mode=request.balance_mode,
                        )
                    except GenerationFailure as exc:
                        failure_reasons[exc.reason] = failure_reasons.get(exc.reason, 0) + 1
                        if exc.reason == "balance_constraints":
                            break
                        continue
                else:
                    available = set(range(1, 46)) - request.fixed_nums - request.exclude_nums
                    remaining = 6 - len(request.fixed_nums)
                    numbers = sorted(list(request.fixed_nums) + random.sample(list(available), remaining))

                if request.limit_consecutive and count_consecutive_pairs(numbers) > 2:
                    failure_reasons["consecutive_limit"] += 1
                    continue

                key = tuple(numbers)
                if key in existing_keys or key in generated_keys:
                    reason = "duplicate_history" if key in existing_keys else "duplicate_batch"
                    failure_reasons[reason] += 1
                    continue

                valid = True
                break

            if not valid:
                failed_count += 1
                continue

            key = tuple(numbers)
            generated_keys.add(key)
            generated_sets.append(numbers)

        result_sets = self.history_manager.add_many(generated_sets)
        dropped_count = max(0, len(generated_sets) - len(result_sets))
        if dropped_count:
            failed_count += dropped_count
            failure_reasons["duplicate_history"] += dropped_count

        return GenerationResult(
            requested_count=request.count,
            generated_sets=result_sets,
            failed_count=failed_count,
            failure_reasons=failure_reasons,
        )


__all__ = ["GenerationRequest", "GenerationResult", "GenerationService"]
