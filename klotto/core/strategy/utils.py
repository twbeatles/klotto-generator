from __future__ import annotations

import json
import math
import random
from typing import Any, Callable, Dict, List, Optional, Sequence




def clamp(value: Any, min_value: float, max_value: float, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(min_value, min(max_value, parsed))


def clamp01(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, value))


def resolve_payout_mode(value: Any) -> str:
    return 'fast_fixed' if value == 'fast_fixed' else 'hybrid_dynamic_first'


def xorshift32(seed: int) -> Callable[[], float]:
    state = seed & 0xFFFFFFFF

    def next_value() -> float:
        nonlocal state
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= (state >> 17) & 0xFFFFFFFF
        state ^= (state << 5) & 0xFFFFFFFF
        return float(state & 0xFFFFFFFF) / 4294967296.0

    return next_value


def create_matrix(size: int) -> List[List[int]]:
    return [[0 for _ in range(size)] for _ in range(size)]


def get_numbers(draw: Optional[Dict[str, Any]]) -> List[int]:
    numbers = draw.get('numbers', []) if isinstance(draw, dict) else []
    return sorted(int(number) for number in numbers if 1 <= int(number) <= 45)


def summarize_series(series: Optional[Sequence[float]] = None) -> Dict[str, float]:
    values = sorted(float(value) for value in (series or []))
    if not values:
        return {'mean': 0.0, 'median': 0.0, 'std': 1.0, 'min': 0.0, 'max': 0.0}
    mean = sum(values) / len(values)
    if len(values) % 2 == 0:
        median = (values[(len(values) // 2) - 1] + values[len(values) // 2]) / 2
    else:
        median = values[len(values) // 2]
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    std = math.sqrt(variance)
    if std <= 0:
        std = max((values[-1] - values[0]) / 4, 1)
    return {'mean': mean, 'median': median, 'std': std, 'min': values[0], 'max': values[-1]}


def normalize_ratio(value: float, max_value: float) -> float:
    if not math.isfinite(value) or not math.isfinite(max_value) or max_value <= 0:
        return 0.0
    return clamp01(value / max_value)


def normalize_around(value: float, center: float = 1.0, radius: float = 1.25) -> float:
    return clamp01(1 - (abs(value - center) / radius))


def compute_delta_affinity(number: int, last_draw: Sequence[int], avg_delta: float) -> float:
    if not avg_delta or not last_draw:
        return 0.5
    best = 0.0
    for base in last_draw:
        diff = abs(abs(number - base) - avg_delta)
        score = clamp01(1 - (diff / max(avg_delta * 1.25, 4)))
        if score > best:
            best = score
    return best


def normalize_weights(weights: Sequence[float]) -> List[float]:
    max_value = max([float(weight) for weight in list(weights)[1:]] or [1.0])
    return [0.0] + [max(float(weight or 0), 0.0) / max_value for weight in list(weights)[1:]]


def create_adaptive_key(normalized: Dict[str, Any], source_data: Sequence[Dict[str, Any]]) -> str:
    last_draw_no = int(source_data[-1].get('draw_no', 0)) if source_data else 0
    return json.dumps(
        {
            'strategyId': normalized.get('strategyId'),
            'lookbackWindow': normalized.get('params', {}).get('lookbackWindow'),
            'simulationCount': normalized.get('params', {}).get('simulationCount'),
            'seed': normalized.get('params', {}).get('seed'),
            'filters': normalized.get('filters') or {},
            'sourceLength': len(source_data),
            'lastDrawNo': last_draw_no,
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def sort_candidate(numbers: Sequence[int]) -> Optional[List[int]]:
    try:
        candidate = sorted(int(number) for number in numbers)
    except (TypeError, ValueError):
        return None
    if len(candidate) != 6:
        return None
    for index in range(1, len(candidate)):
        if candidate[index] == candidate[index - 1] or candidate[index] < 1 or candidate[index] > 45:
            return None
    if candidate[0] < 1 or candidate[-1] > 45:
        return None
    return candidate


def score_by_distance(value: float, stats: Optional[Dict[str, float]] = None, fallback_spread: float = 10) -> float:
    stats = stats or {}
    median = float(stats.get('median', value))
    std = float(stats.get('std', 1))
    spread = max(std * 1.6, fallback_spread, 1)
    return clamp01(1 - (abs(value - median) / spread))


def get_recommendation_mix(strategy_id: str) -> Dict[str, float]:
    if strategy_id == 'pair_cooccurrence':
        return {'weight': 0.30, 'pair': 0.40, 'profile': 0.15, 'gap': 0.15}
    if strategy_id == 'stat_ac_sum':
        return {'weight': 0.30, 'pair': 0.15, 'profile': 0.40, 'gap': 0.15}
    if strategy_id in {'balance_oe_hl', 'zone_split_3band', 'last_digit_balance'}:
        return {'weight': 0.28, 'pair': 0.12, 'profile': 0.45, 'gap': 0.15}
    if strategy_id in {'cold_frequency', 'mean_reversion_cycle', 'skip_hit_weighted'}:
        return {'weight': 0.28, 'pair': 0.14, 'profile': 0.20, 'gap': 0.38}
    if strategy_id in {'momentum_recent', 'hot_frequency', 'adjacency_bias'}:
        return {'weight': 0.40, 'pair': 0.20, 'profile': 0.18, 'gap': 0.22}
    if strategy_id in {'consensus_portfolio', 'bayesian_smooth'}:
        return {'weight': 0.34, 'pair': 0.22, 'profile': 0.24, 'gap': 0.20}
    return {'weight': 0.34, 'pair': 0.20, 'profile': 0.24, 'gap': 0.22}


def count_overlap(left: Sequence[int], right: Sequence[int]) -> int:
    right_set = set(right)
    return sum(1 for value in left if value in right_set)


def pick_diverse_candidates(candidates: Sequence[Dict[str, Any]], set_count: int = 5) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    overlap_caps = [3, 4, 5] if set_count > 3 else [4, 5]
    for cap in overlap_caps:
        for candidate in candidates:
            if len(selected) >= set_count:
                break
            if any(item['key'] == candidate['key'] for item in selected):
                continue
            if all(count_overlap(item['set'], candidate['set']) <= cap for item in selected):
                selected.append(candidate)
        if len(selected) >= set_count:
            break
    if len(selected) < set_count:
        for candidate in candidates:
            if len(selected) >= set_count:
                break
            if any(item['key'] == candidate['key'] for item in selected):
                continue
            selected.append(candidate)
    return selected[:set_count]


