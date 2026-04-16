from __future__ import annotations

import json
import math
import random
from typing import Any, Callable, Dict, List, Optional, Sequence

from klotto.core.strategy_catalog import AUTO_STRATEGY_IDS, create_default_strategy_request, get_strategy_meta, resolve_strategy_id
from klotto.core.strategy_filters import AdvancedMonteCarlo, create_filter_evaluator, passes_filters, sanitize_filters

FIXED_PRIZE_BY_RANK = {
    1: 2_000_000_000,
    2: 50_000_000,
    3: 1_500_000,
    4: 50_000,
    5: 5_000,
}

ADAPTIVE_SOURCE_STRATEGIES = [
    'consensus_portfolio',
    'ensemble_weighted',
    'bayesian_smooth',
    'momentum_recent',
    'mean_reversion_cycle',
    'zone_split_3band',
    'stat_ac_sum',
    'pair_cooccurrence',
    'adjacency_bias',
    'recency_gap',
    'balance_oe_hl',
    'hot_frequency',
    'cold_frequency',
]


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


class StrategyEngine:
    def __init__(self, winning_stats: Optional[Sequence[Dict[str, Any]]] = None):
        self.data = sorted(
            [dict(item) for item in (winning_stats or []) if item and str(item.get('draw_no', '')).strip()],
            key=lambda row: int(row.get('draw_no', 0)),
        )
        self._analysis_cache: Dict[str, Dict[str, Any]] = {}

    def normalize_request(self, raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raw = raw or {}
        base = create_default_strategy_request(resolve_strategy_id(raw.get('strategyId')))
        meta = get_strategy_meta(base['strategyId'])
        params = {**base['params'], **(raw.get('params') or {})}
        params['simulationCount'] = int(clamp(params.get('simulationCount'), 1000, 20000, base['params']['simulationCount']))
        params['lookbackWindow'] = int(clamp(params.get('lookbackWindow'), 5, 120, base['params']['lookbackWindow']))
        params['wheelPoolSize'] = None if params.get('wheelPoolSize') is None else int(clamp(params.get('wheelPoolSize'), 7, 20, meta['defaultParams'].get('wheelPoolSize') or 10))
        params['wheelGuarantee'] = None if params.get('wheelGuarantee') is None else int(clamp(params.get('wheelGuarantee'), 2, 5, meta['defaultParams'].get('wheelGuarantee') or 3))
        raw_seed = (raw.get('params') or {}).get('seed')
        params['seed'] = int(raw_seed) if raw_seed not in (None, '', []) and str(raw_seed).lstrip('-').isdigit() else None
        params['payoutMode'] = resolve_payout_mode(params.get('payoutMode'))
        filters = sanitize_filters({**base['filters'], **(raw.get('filters') or {})})
        return {
            'strategyId': meta['id'],
            'evidenceTier': meta['tier'],
            'params': params,
            'filters': filters,
        }

    def get_data_before(self, draw_no: Optional[int] = None) -> List[Dict[str, Any]]:
        if draw_no is None:
            return list(self.data)
        return [row for row in self.data if int(row.get('draw_no', 0)) < int(draw_no)]

    def get_random_fn(self, seed: Optional[int] = None) -> Callable[[], float]:
        if seed in (None, '', []):
            return random.random
        try:
            return xorshift32(int(seed))
        except (TypeError, ValueError):
            return random.random

    def build_context(self, source_data: Sequence[Dict[str, Any]], lookback_window: int = 20) -> Dict[str, Any]:
        data = sorted([dict(item) for item in source_data], key=lambda row: int(row.get('draw_no', 0)))
        total_draws = len(data)
        normalized_lookback = max(1, int(lookback_window or 20))
        recent = data[-normalized_lookback:]
        recent_draw_count = len(recent)
        freq = [0] * 46
        recent_freq = [0] * 46
        last_seen = [-1] * 46
        pending_gap = [total_draws or 0] * 46
        average_gap = [0.0] * 46
        pair_counts = [0] * 46
        recent_pair_counts = [0] * 46
        pair_matrix = create_matrix(46)
        recent_pair_matrix = create_matrix(46)
        end_digit_recent = [0] * 10
        zone_recent = [0, 0, 0]
        appearance_indexes: List[List[int]] = [[] for _ in range(46)]
        draw_sums: List[int] = []
        draw_acs: List[int] = []
        recent_sums: List[int] = []
        recent_acs: List[int] = []

        for idx, draw in enumerate(data):
            numbers = get_numbers(draw)
            if not numbers:
                continue
            draw_sums.append(AdvancedMonteCarlo.calculate_sum(numbers))
            draw_acs.append(AdvancedMonteCarlo.calculate_ac(numbers))
            for number in numbers:
                freq[number] += 1
                last_seen[number] = idx
                appearance_indexes[number].append(idx)
            for i in range(len(numbers)):
                for j in range(i + 1, len(numbers)):
                    left = numbers[i]
                    right = numbers[j]
                    pair_counts[left] += 1
                    pair_counts[right] += 1
                    pair_matrix[left][right] += 1
                    pair_matrix[right][left] += 1

        for draw in recent:
            numbers = get_numbers(draw)
            if not numbers:
                continue
            recent_sums.append(AdvancedMonteCarlo.calculate_sum(numbers))
            recent_acs.append(AdvancedMonteCarlo.calculate_ac(numbers))
            for number in numbers:
                recent_freq[number] += 1
                end_digit_recent[number % 10] += 1
                if number <= 15:
                    zone_recent[0] += 1
                elif number <= 30:
                    zone_recent[1] += 1
                else:
                    zone_recent[2] += 1
            for i in range(len(numbers)):
                for j in range(i + 1, len(numbers)):
                    left = numbers[i]
                    right = numbers[j]
                    recent_pair_counts[left] += 1
                    recent_pair_counts[right] += 1
                    recent_pair_matrix[left][right] += 1
                    recent_pair_matrix[right][left] += 1

        for number in range(1, 46):
            indexes = appearance_indexes[number]
            if not indexes:
                average_gap[number] = total_draws if total_draws > 0 else normalized_lookback
                pending_gap[number] = total_draws if total_draws > 0 else 0
                continue
            if len(indexes) == 1:
                average_gap[number] = max(total_draws / max(len(indexes), 1), 1)
            else:
                gap_sum = 0
                for idx in range(1, len(indexes)):
                    gap_sum += indexes[idx] - indexes[idx - 1]
                average_gap[number] = max(gap_sum / max(len(indexes) - 1, 1), 1)
            pending_gap[number] = max((total_draws - 1) - indexes[-1], 0)

        pair_matrix_max = 1
        recent_pair_matrix_max = 1
        for left in range(1, 46):
            for right in range(left + 1, 46):
                pair_matrix_max = max(pair_matrix_max, pair_matrix[left][right])
                recent_pair_matrix_max = max(recent_pair_matrix_max, recent_pair_matrix[left][right])

        return {
            'totalDraws': total_draws,
            'lookbackWindow': normalized_lookback,
            'recentDrawCount': recent_draw_count,
            'freq': freq,
            'recentFreq': recent_freq,
            'lastSeen': last_seen,
            'pendingGap': pending_gap,
            'averageGap': average_gap,
            'pairCounts': pair_counts,
            'recentPairCounts': recent_pair_counts,
            'pairMatrix': pair_matrix,
            'recentPairMatrix': recent_pair_matrix,
            'pairMatrixMax': pair_matrix_max,
            'recentPairMatrixMax': recent_pair_matrix_max,
            'endDigitRecent': end_digit_recent,
            'zoneRecent': zone_recent,
            'lastDraw': get_numbers(data[-1]) if total_draws else [],
            'drawSums': draw_sums,
            'drawAcs': draw_acs,
            'recentSums': recent_sums,
            'recentAcs': recent_acs,
            'drawSumStats': summarize_series(draw_sums),
            'drawAcStats': summarize_series(draw_acs),
            'recentSumStats': summarize_series(recent_sums),
            'recentAcStats': summarize_series(recent_acs),
        }

    def compute_weights(self, request: Dict[str, Any], source_data: Sequence[Dict[str, Any]], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        normalized = self.normalize_request(request)
        return self.compute_weights_from_normalized(normalized, source_data, options or {})

    def get_adaptive_candidate_strategies(self) -> List[str]:
        return list(ADAPTIVE_SOURCE_STRATEGIES)

    def create_strategy_variant_request(self, normalized: Dict[str, Any], strategy_id: str) -> Dict[str, Any]:
        return {
            **normalized,
            'strategyId': strategy_id,
            'evidenceTier': get_strategy_meta(strategy_id)['tier'],
            'params': dict(normalized.get('params', {})),
            'filters': dict(normalized.get('filters', {})),
        }

    def evaluate_recent_strategy_performance(self, normalized: Dict[str, Any], source_data: Sequence[Dict[str, Any]], strategy_id: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        options = options or {}
        evaluation_window = min(max(int(options.get('evaluationWindow') or normalized['params'].get('lookbackWindow', 20)), 10), 30)
        evaluation_set_count = min(max(int(options.get('evaluationSetCount') or 5), 3), 5)
        simulation_count = min(max(int(options.get('simulationCount') or normalized['params'].get('simulationCount', 5000)), 1200), 2400)
        start_idx = max(1, len(source_data) - evaluation_window)
        draws = total_sets = total_hit_count = total_best_hit = 0
        best4_plus_draws = best3_plus_draws = 0
        rank_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

        for idx in range(start_idx, len(source_data)):
            history = list(source_data[:idx])
            actual = source_data[idx]
            if not history or not actual.get('numbers'):
                continue
            engine = StrategyEngine(history)
            eval_request = self.create_strategy_variant_request(normalized, strategy_id)
            seed_base = normalized['params'].get('seed') if normalized['params'].get('seed') is not None else 2026
            eval_request['params'] = {
                **eval_request['params'],
                'simulationCount': simulation_count,
                'seed': int(seed_base) + (idx * 37) + (len(strategy_id) * 17),
            }
            result = engine.recommend_from_simulation(eval_request, {'setCount': evaluation_set_count})
            sets = result.get('sets', [])
            if not sets:
                continue
            draws += 1
            total_sets += len(sets)
            best_hit = 0
            actual_numbers = set(int(number) for number in actual.get('numbers', []))
            for ticket in sets:
                hit_count = sum(1 for value in ticket if value in actual_numbers)
                total_hit_count += hit_count
                best_hit = max(best_hit, hit_count)
                rank = engine.rank_ticket(ticket, actual.get('numbers', []), int(actual.get('bonus', 0)))
                if 1 <= rank <= 5:
                    rank_counts[rank] += 1
            total_best_hit += best_hit
            if best_hit >= 4:
                best4_plus_draws += 1
            if best_hit >= 3:
                best3_plus_draws += 1

        avg_best_hit = total_best_hit / max(draws, 1)
        avg_hit_per_set = total_hit_count / max(total_sets, 1)
        draw_rate_best4_plus = (best4_plus_draws / max(draws, 1)) * 100
        draw_rate_best3_plus = (best3_plus_draws / max(draws, 1)) * 100
        composite_score = (avg_best_hit * 100) + (draw_rate_best4_plus * 4.0) + (draw_rate_best3_plus * 1.5) + (avg_hit_per_set * 12)
        return {
            'strategyId': strategy_id,
            'draws': draws,
            'avgBestHit': round(avg_best_hit, 4),
            'avgHitPerSet': round(avg_hit_per_set, 4),
            'drawRateBest4Plus': round(draw_rate_best4_plus, 2),
            'drawRateBest3Plus': round(draw_rate_best3_plus, 2),
            'compositeScore': round(composite_score, 4),
            'rankCounts': rank_counts,
        }

    def resolve_adaptive_weights(self, normalized: Dict[str, Any], source_data: Sequence[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
        cache_key = create_adaptive_key(normalized, source_data)
        if cache_key in self._analysis_cache:
            return self._analysis_cache[cache_key]
        evaluation_window = min(max(int(normalized['params'].get('lookbackWindow', 20)), 10), 30)
        ranking = [self.evaluate_recent_strategy_performance(normalized, source_data, strategy_id, {'evaluationWindow': evaluation_window}) for strategy_id in self.get_adaptive_candidate_strategies()]
        ranking = [row for row in ranking if row['draws'] > 0]
        ranking.sort(key=lambda row: (-float(row.get('compositeScore', 0)), -float(row.get('avgBestHit', 0)), str(row.get('strategyId', ''))))
        fallback_id = 'consensus_portfolio'
        selected_rows = ranking[:1] if normalized['strategyId'] == 'auto_recent_top' else ranking[:3]
        if not selected_rows:
            selected_rows = [{
                'strategyId': fallback_id,
                'draws': 0,
                'avgBestHit': 0,
                'avgHitPerSet': 0,
                'drawRateBest4Plus': 0,
                'drawRateBest3Plus': 0,
                'compositeScore': 1,
                'rankCounts': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
            }]
        selected_strategies = []
        for row in selected_rows:
            request = self.create_strategy_variant_request(normalized, row['strategyId'])
            computed = self.compute_weights_from_normalized(request, source_data, {'context': context})
            selected_strategies.append({**row, 'weights': computed['weights']})
        weights = list(selected_strategies[0]['weights'])
        if normalized['strategyId'] == 'auto_ensemble_top3':
            strengths = [max(float(item.get('compositeScore', 0)), 1 + (len(selected_strategies) - index)) for index, item in enumerate(selected_strategies)]
            strength_sum = sum(strengths) or 1.0
            normalized_vectors = [normalize_weights(item['weights']) for item in selected_strategies]
            weights = [0.0] * 46
            for number in range(1, 46):
                blended = 0.0
                for index, _item in enumerate(selected_strategies):
                    blended += normalized_vectors[index][number] * (strengths[index] / strength_sum)
                weights[number] = max(blended, 0.0001)
        adaptive = {
            'mode': 'recent_top_1' if normalized['strategyId'] == 'auto_recent_top' else 'recent_top_3_blend',
            'evaluationWindow': evaluation_window,
            'selectedStrategies': [
                {
                    'strategyId': item['strategyId'],
                    'avgBestHit': item['avgBestHit'],
                    'avgHitPerSet': item['avgHitPerSet'],
                    'drawRateBest4Plus': item['drawRateBest4Plus'],
                    'drawRateBest3Plus': item['drawRateBest3Plus'],
                    'compositeScore': item['compositeScore'],
                }
                for item in selected_strategies
            ],
            'ranking': [
                {
                    'strategyId': item['strategyId'],
                    'avgBestHit': item['avgBestHit'],
                    'avgHitPerSet': item['avgHitPerSet'],
                    'drawRateBest4Plus': item['drawRateBest4Plus'],
                    'drawRateBest3Plus': item['drawRateBest3Plus'],
                    'compositeScore': item['compositeScore'],
                }
                for item in ranking[:5]
            ],
        }
        resolved = {'weights': weights, 'adaptive': adaptive}
        self._analysis_cache[cache_key] = resolved
        return resolved

    def compute_weights_from_normalized(self, normalized: Dict[str, Any], source_data: Sequence[Dict[str, Any]], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        options = options or {}
        context = options.get('context') or self.build_context(source_data, normalized['params']['lookbackWindow'])
        if normalized['strategyId'] in AUTO_STRATEGY_IDS:
            adaptive = self.resolve_adaptive_weights(normalized, source_data, context)
            return {'weights': adaptive['weights'], 'request': normalized, 'context': context, 'adaptive': adaptive['adaptive']}
        total_draws = context['totalDraws']
        recent_draw_count = context['recentDrawCount']
        freq = context['freq']
        recent_freq = context['recentFreq']
        pending_gap = context['pendingGap']
        average_gap = context['averageGap']
        pair_counts = context['pairCounts']
        recent_pair_counts = context['recentPairCounts']
        end_digit_recent = context['endDigitRecent']
        zone_recent = context['zoneRecent']
        last_draw = context['lastDraw']
        weights = [1.0] * 46
        freq_max = max(freq[1:] or [1])
        recent_max = max(recent_freq[1:] or [1])
        pair_max = max(pair_counts[1:] or [1])
        recent_pair_max = max(recent_pair_counts[1:] or [1])
        end_max = max(end_digit_recent or [1])
        zone_max = max(zone_recent or [1])
        total_window = max(total_draws, 1)
        recent_window = max(recent_draw_count, 1)
        is_wheel = normalized['strategyId'] in {'wheel_full', 'wheel_reduced_t3'}
        is_adjacency = normalized['strategyId'] == 'adjacency_bias'
        is_delta_pattern = normalized['strategyId'] == 'delta_gap_pattern'
        last_draw_set = set(last_draw) if is_adjacency or normalized['strategyId'] == 'carryover_repeat_control' else None
        avg_delta = 0.0
        if is_delta_pattern and len(last_draw) >= 2:
            avg_delta = sum(last_draw[idx + 1] - last_draw[idx] for idx in range(len(last_draw) - 1)) / max(len(last_draw) - 1, 1)
        bayes_values = [0.0] * 46
        for number in range(1, 46):
            bayes_values[number] = (freq[number] + (recent_freq[number] * 1.5) + 1) / (total_window + (recent_window * 1.5) + 2)
        bayes_max = max(bayes_values[1:] or [0.0001])
        for number in range(1, 46):
            g = normalize_ratio(freq[number], freq_max)
            r = normalize_ratio(recent_freq[number], recent_max)
            gap_count = float(pending_gap[number]) if math.isfinite(float(pending_gap[number])) else 0.0
            avg_gap = max(float(average_gap[number] or 1), 1.0)
            overdue_ratio = min((gap_count + 1) / avg_gap, 3)
            overdue_norm = clamp01(overdue_ratio / 3)
            gap_balance = normalize_around(overdue_ratio, 1.05, 1.45)
            p = normalize_ratio(pair_counts[number], pair_max)
            recent_pair = normalize_ratio(recent_pair_counts[number], recent_pair_max)
            zone_idx = 0 if number <= 15 else (1 if number <= 30 else 2)
            zone_bal = 1 - normalize_ratio(zone_recent[zone_idx], zone_max)
            end_bal = 1 - normalize_ratio(end_digit_recent[number % 10], end_max)
            long_rate = freq[number] / total_window
            recent_rate = recent_freq[number] / recent_window
            lift_raw = (recent_rate / long_rate) if long_rate > 0 else (2 if recent_rate > 0 else 1)
            momentum_norm = clamp01((lift_raw - 0.5) / 1.5)
            reverse_momentum = 1 - momentum_norm
            stability = clamp01(1 - (abs(recent_rate - long_rate) / max(long_rate, 1 / total_window)))
            bayes = clamp01(bayes_values[number] / bayes_max)
            adj = 0.0
            if last_draw_set and number in last_draw_set:
                adj += 0.2
            if last_draw_set and (number - 1) in last_draw_set:
                adj += 0.45
            if last_draw_set and (number + 1) in last_draw_set:
                adj += 0.45
            delta_affinity = compute_delta_affinity(number, last_draw, avg_delta)
            hot_core = (g * 0.35) + (r * 0.35) + (momentum_norm * 0.30)
            cold_core = (overdue_norm * 0.55) + ((1 - g) * 0.20) + (reverse_momentum * 0.25)
            balance_core = (zone_bal * 0.45) + (end_bal * 0.20) + (stability * 0.15) + (gap_balance * 0.20)
            pair_core = (recent_pair * 0.55) + (p * 0.30) + (r * 0.15)
            consensus_core = (hot_core * 0.25) + (cold_core * 0.20) + (pair_core * 0.20) + (balance_core * 0.15) + (bayes * 0.20)
            strategy_id = normalized['strategyId']
            if strategy_id == 'random_baseline':
                weight = 1.0
            elif strategy_id == 'ensemble_weighted':
                weight = 0.6 + (bayes * 0.35) + (r * 0.35) + (overdue_norm * 0.20) + (gap_balance * 0.20) + (recent_pair * 0.15) + (zone_bal * 0.10)
            elif strategy_id == 'consensus_portfolio':
                weight = 0.65 + (consensus_core * 1.10) + (gap_balance * 0.15)
            elif strategy_id == 'bayesian_smooth':
                weight = 0.7 + (bayes * 0.80) + (stability * 0.25) + (r * 0.20) + (zone_bal * 0.15)
            elif strategy_id == 'momentum_recent':
                weight = 0.65 + (hot_core * 0.95) + (recent_pair * 0.20) + (bayes * 0.10)
            elif strategy_id == 'mean_reversion_cycle':
                weight = 0.65 + (cold_core * 1.00) + (gap_balance * 0.25) + (zone_bal * 0.10)
            elif strategy_id == 'hot_frequency':
                weight = 0.7 + (hot_core * 0.95) + (bayes * 0.10)
            elif strategy_id == 'cold_frequency':
                weight = 0.7 + (cold_core * 0.95) + (gap_balance * 0.25)
            elif strategy_id == 'recency_gap':
                weight = 0.65 + (r * 0.35) + (overdue_norm * 0.65) + (gap_balance * 0.35) + (momentum_norm * 0.15)
            elif strategy_id == 'balance_oe_hl':
                weight = 0.75 + (balance_core * 0.90) + (bayes * 0.15)
            elif strategy_id == 'stat_ac_sum':
                weight = 0.75 + (bayes * 0.35) + (pair_core * 0.25) + (gap_balance * 0.15) + (stability * 0.25)
            elif strategy_id == 'pair_cooccurrence':
                weight = 0.7 + (pair_core * 1.00) + (bayes * 0.10)
            elif strategy_id == 'adjacency_bias':
                weight = 0.65 + (hot_core * 0.40) + (adj * 0.90) + (gap_balance * 0.10)
            elif strategy_id == 'zone_split_3band':
                weight = 0.7 + (zone_bal * 0.75) + (end_bal * 0.25) + (r * 0.20) + (bayes * 0.15)
            elif strategy_id in {'wheel_full', 'wheel_reduced_t3'}:
                weight = 0.75 + (bayes * 0.30) + (hot_core * 0.35) + (pair_core * 0.25)
            elif strategy_id == 'skip_hit_weighted':
                weight = 0.65 + (overdue_norm * 0.80) + (gap_balance * 0.45) + (reverse_momentum * 0.15)
            elif strategy_id == 'last_digit_balance':
                weight = 0.7 + (end_bal * 0.85) + (balance_core * 0.20) + (g * 0.15)
            elif strategy_id == 'delta_gap_pattern':
                weight = 0.65 + (delta_affinity * 0.85) + (bayes * 0.20) + (r * 0.15)
            elif strategy_id == 'carryover_repeat_control':
                repeat_penalty = 0.45 if last_draw_set and number in last_draw_set else 1.0
                weight = (0.7 + (cold_core * 0.45) + (bayes * 0.15) + (gap_balance * 0.20)) * repeat_penalty
            else:
                weight = 0.7 + (consensus_core * 0.95)
            weights[number] = max(weight, 0.0001 if is_wheel else weight)
        return {'weights': weights, 'request': normalized, 'context': context, 'adaptive': None}

    def prepare_execution(self, request: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        options = options or {}
        normalized_request = options.get('normalizedRequest') or self.normalize_request(request)
        source_data = options.get('sourceData') or self.data
        rng = options.get('rng') or self.get_random_fn(normalized_request['params'].get('seed'))
        computed = self.compute_weights_from_normalized(normalized_request, source_data, {'context': options.get('context')})
        is_wheel = normalized_request['strategyId'] in {'wheel_full', 'wheel_reduced_t3'}
        return {
            'normalizedRequest': normalized_request,
            'sourceData': source_data,
            'rng': rng,
            'weights': computed['weights'],
            'isWheel': is_wheel,
            'context': computed['context'],
            'adaptive': computed.get('adaptive'),
        }

    def sample_with_constraints(self, weights: Sequence[float], fixed: Optional[Sequence[int]] = None, exclude: Optional[Sequence[int]] = None, rng: Optional[Callable[[], float]] = None) -> Optional[List[int]]:
        rng = rng or random.random
        fixed_unique = sorted({int(number) for number in (fixed or []) if 1 <= int(number) <= 45})
        exclude_set = {int(number) for number in (exclude or []) if 1 <= int(number) <= 45}
        for number in fixed_unique:
            exclude_set.discard(number)
        needed = 6 - len(fixed_unique)
        if needed < 0:
            return None
        pool = [{'n': number, 'w': max(0.0001, float(weights[number] if number < len(weights) else 1))} for number in range(1, 46) if number not in exclude_set and number not in fixed_unique]
        if len(pool) < needed:
            return None
        chosen = list(fixed_unique)
        while len(chosen) < 6:
            total = sum(item['w'] for item in pool)
            threshold = rng() * total
            index = 0
            for current_index, item in enumerate(pool):
                threshold -= item['w']
                if threshold <= 0:
                    index = current_index
                    break
            chosen.append(pool[index]['n'])
            pool.pop(index)
        return sorted(chosen)

    def generate_wheel_set(self, weights: Sequence[float], request: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> Optional[List[int]]:
        options = options or {}
        fixed = sorted({int(number) for number in (options.get('fixed') or []) if 1 <= int(number) <= 45})
        exclude = [int(number) for number in (options.get('exclude') or []) if 1 <= int(number) <= 45]
        rng = options.get('rng') or random.random
        pool_size = int(request['params'].get('wheelPoolSize') or 10)
        guarantee = int(request['params'].get('wheelGuarantee') or 3)
        seed_set = self.sample_with_constraints(weights, fixed, exclude, rng)
        if not seed_set:
            return None
        candidates: List[int] = []
        exclude_set = set(exclude)
        available = [number for number in range(1, 46) if number not in exclude_set]
        sorted_by_weight = sorted(available, key=lambda number: float(weights[number] if number < len(weights) else 1), reverse=True)
        for number in sorted_by_weight:
            if number not in candidates:
                candidates.append(number)
            if len(candidates) >= pool_size:
                break
        while len(candidates) < pool_size:
            number = int(rng() * 45) + 1
            if number not in exclude_set and number not in candidates:
                candidates.append(number)
        output = list(fixed)
        seed_extras = [number for number in seed_set if number not in output]
        min_base_size = max(min(max(guarantee, 1), 6), len(output))
        while len(output) < min_base_size and seed_extras:
            output.append(seed_extras.pop(0))
        dynamic_pool = [number for number in candidates if number not in output]
        while len(output) < 6 and dynamic_pool:
            idx = int(rng() * len(dynamic_pool))
            output.append(dynamic_pool.pop(idx))
        return sorted(output) if len(output) == 6 else None

    def generate_set_with_execution(self, execution: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> Optional[List[int]]:
        options = options or {}
        normalized = execution['normalizedRequest']
        filter_evaluator = options.get('filterEvaluator') or create_filter_evaluator(normalized.get('filters'))
        max_attempts = int(options.get('maxAttempts') or 250)
        fixed = options.get('fixed') or []
        exclude = options.get('exclude') or []
        rng = options.get('rng') or execution['rng']
        for _ in range(max_attempts):
            candidate = self.generate_wheel_set(execution['weights'], normalized, {'fixed': fixed, 'exclude': exclude, 'rng': rng}) if execution['isWheel'] else self.sample_with_constraints(execution['weights'], fixed, exclude, rng)
            if candidate and filter_evaluator(candidate, True):
                return candidate
        fallback_weights = [1.0] * 46
        for _ in range(120):
            fallback = self.sample_with_constraints(fallback_weights, fixed, exclude, rng)
            if fallback and filter_evaluator(fallback, True):
                return fallback
        return None

    def generate_set(self, request: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> Optional[List[int]]:
        options = options or {}
        execution = options.get('execution') or self.prepare_execution(request, options)
        return self.generate_set_with_execution(execution, options)

    def generate_multiple_sets(self, count: int, request: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> List[List[int]]:
        options = options or {}
        quantity = max(1, int(count or 1))
        unique: set[str] = set()
        result: List[List[int]] = []
        execution = options.get('execution') or self.prepare_execution(request, options)
        filter_evaluator = options.get('filterEvaluator') or create_filter_evaluator(execution['normalizedRequest'].get('filters'))
        rng = options.get('rng') or execution['rng']
        attempts = 0
        max_attempts = max(200, quantity * 80)
        per_set_max_attempts = int(options.get('maxAttempts') or 250)
        while len(result) < quantity and attempts < max_attempts:
            attempts += 1
            current = self.generate_set_with_execution(execution, {**options, 'rng': rng, 'maxAttempts': per_set_max_attempts, 'filterEvaluator': filter_evaluator})
            if not current or len(current) != 6:
                continue
            key = ','.join(str(value) for value in current)
            if key in unique:
                continue
            unique.add(key)
            result.append(current)
        return result

    def simulate_weights(self, request: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        options = options or {}
        execution = options.get('execution') or self.prepare_execution(request, options)
        normalized = execution['normalizedRequest']
        rng = options.get('rng') or self.get_random_fn(normalized['params'].get('seed'))
        sim_count = int(normalized['params'].get('simulationCount') or 5000)
        counts = [0] * 46
        filter_evaluator = options.get('filterEvaluator') or create_filter_evaluator(normalized.get('filters'))
        accepted = 0
        for _ in range(sim_count):
            current = self.generate_wheel_set(execution['weights'], normalized, {'rng': rng}) if execution['isWheel'] else self.sample_with_constraints(execution['weights'], [], [], rng)
            if not current or not filter_evaluator(current, True):
                continue
            for number in current:
                counts[number] += 1
            accepted += 1
        if accepted == 0:
            return {'weights': [1] * 46, 'request': normalized, 'diagnostics': {'accepted': 0, 'simulationCount': sim_count, 'fallbackMode': 'uniform_weights'}}
        return {'weights': counts, 'request': normalized, 'diagnostics': {'accepted': accepted, 'simulationCount': sim_count, 'fallbackMode': 'none'}}

    def score_set_candidate(self, numbers: Sequence[int], request: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        options = options or {}
        candidate = sort_candidate(numbers)
        if not candidate:
            return None
        normalized = options.get('normalizedRequest') or options.get('execution', {}).get('normalizedRequest') or self.normalize_request(request)
        source_data = options.get('sourceData') or options.get('execution', {}).get('sourceData') or self.data
        if options.get('execution'):
            computed = {
                'weights': options.get('weights') or options['execution']['weights'],
                'context': options.get('context') or options['execution']['context'],
                'adaptive': options['execution'].get('adaptive'),
            }
        else:
            computed = self.compute_weights_from_normalized(normalized, source_data, {'context': options.get('context')})
        weights = options.get('weights') or computed['weights']
        context = options.get('context') or computed['context'] or self.build_context(source_data, normalized['params']['lookbackWindow'])
        weight_max = max(weights[1:] or [1])
        pair_matrix = context.get('recentPairMatrix') or context.get('pairMatrix') or []
        pair_matrix_max = max(context.get('recentPairMatrixMax', 0), context.get('pairMatrixMax', 0), 1)
        pending_gap = context.get('pendingGap') or []
        average_gap = context.get('averageGap') or []
        last_draw_set = set(context.get('lastDraw') or [])
        score_mix = get_recommendation_mix(normalized['strategyId'])
        weight_score = sum((weights[number] or 0) / weight_max for number in candidate) / len(candidate)
        pair_synergy_raw = 0.0
        pair_count = 0
        for i in range(len(candidate)):
            for j in range(i + 1, len(candidate)):
                pair_synergy_raw += (pair_matrix[candidate[i]][candidate[j]] if pair_matrix else 0) / pair_matrix_max
                pair_count += 1
        pair_synergy = (pair_synergy_raw / pair_count) if pair_count else 0.0
        gap_balance_score = 0.0
        for number in candidate:
            ratio = min(((pending_gap[number] or 0) + 1) / max(average_gap[number] or 1, 1), 3)
            gap_balance_score += clamp01(1 - (abs(ratio - 1.05) / 1.45))
        gap_balance_score /= len(candidate)
        set_sum = AdvancedMonteCarlo.calculate_sum(candidate)
        ac = AdvancedMonteCarlo.calculate_ac(candidate)
        sum_score = score_by_distance(set_sum, context.get('recentSumStats') or context.get('drawSumStats'), 24)
        ac_score = score_by_distance(ac, context.get('recentAcStats') or context.get('drawAcStats'), 1.75)
        zone_coverage = len({0 if number <= 15 else (1 if number <= 30 else 2) for number in candidate}) / 3
        end_digit_score = len({number % 10 for number in candidate}) / 6
        overlap_last = sum(1 for number in candidate if number in last_draw_set)
        carry_score = clamp01(1 - (max(overlap_last - 1, 0) / 3))
        profile_score = (sum_score * 0.32) + (ac_score * 0.28) + (zone_coverage * 0.20) + (end_digit_score * 0.10) + (carry_score * 0.10)
        total_score = (weight_score * score_mix['weight']) + (pair_synergy * score_mix['pair']) + (profile_score * score_mix['profile']) + (gap_balance_score * score_mix['gap'])
        return {
            'score': round(total_score, 6),
            'breakdown': {
                'weightScore': round(weight_score, 6),
                'pairSynergy': round(pair_synergy, 6),
                'gapBalanceScore': round(gap_balance_score, 6),
                'profileScore': round(profile_score, 6),
                'sumScore': round(sum_score, 6),
                'acScore': round(ac_score, 6),
                'zoneCoverage': round(zone_coverage, 6),
                'endDigitScore': round(end_digit_score, 6),
                'carryScore': round(carry_score, 6),
                'overlapLast': overlap_last,
            },
        }

    def recommend_from_simulation(self, request: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        options = options or {}
        set_count = max(1, int(options.get('setCount') or 5))
        execution = options.get('execution') or self.prepare_execution(request, options)
        simulation = self.simulate_weights(request, {**options, 'execution': execution})
        rng = options.get('rng') or self.get_random_fn(simulation['request']['params'].get('seed'))
        filter_evaluator = options.get('filterEvaluator') or create_filter_evaluator(simulation['request'].get('filters'))
        unique: Dict[str, Dict[str, Any]] = {}
        output: List[List[int]] = []
        attempts = 0
        candidate_pool_target = max(set_count * 40, 140)
        max_attempts = max(500, candidate_pool_target * 14)
        while len(unique) < candidate_pool_target and attempts < max_attempts:
            attempts += 1
            candidate = self.sample_with_constraints(simulation['weights'], [], [], rng)
            if not candidate or not filter_evaluator(candidate, True):
                continue
            key = ','.join(str(value) for value in candidate)
            if key in unique:
                continue
            scored = self.score_set_candidate(candidate, simulation['request'], {
                'execution': execution,
                'normalizedRequest': simulation['request'],
                'sourceData': execution['sourceData'],
                'context': execution['context'],
                'weights': simulation['weights'],
            })
            unique[key] = {'key': key, 'set': candidate, 'score': scored['score'] if scored else 0, 'breakdown': scored['breakdown'] if scored else None}
        ranked_candidates = sorted(unique.values(), key=lambda item: (-float(item.get('score', 0)), item['key']))
        selected = pick_diverse_candidates(ranked_candidates, set_count)
        for item in selected:
            output.append(item['set'])
        if len(output) < set_count:
            remains = self.generate_multiple_sets(set_count - len(output), simulation['request'], {'execution': execution, 'rng': rng, 'filterEvaluator': filter_evaluator})
            for current in remains:
                key = ','.join(str(value) for value in current)
                if not any(','.join(str(v) for v in item) == key for item in output):
                    output.append(current)
        return {
            'sets': output,
            'simulation': {
                **simulation,
                'diagnostics': {
                    **(simulation.get('diagnostics') or {}),
                    'adaptive': execution.get('adaptive'),
                    'effectiveAdaptiveWindow': execution.get('adaptive', {}).get('evaluationWindow') if execution.get('adaptive') else None,
                    'uniqueCandidates': len(ranked_candidates),
                    'candidatePoolTarget': candidate_pool_target,
                    'reranked': True,
                    'selectedCount': len(output),
                    'topScore': float(selected[0]['score']) if selected else 0.0,
                },
            },
        }

    def explain_set(self, numbers: Sequence[int], request: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        options = options or {}
        candidate = sort_candidate(numbers)
        if not candidate:
            return None
        normalized = self.normalize_request(request)
        source_data = options.get('sourceData') or self.data
        computed = self.compute_weights_from_normalized(normalized, source_data, {'context': options.get('context')})
        weights = computed['weights']
        context = computed['context']
        adaptive = computed.get('adaptive')
        total_draws = max(context['totalDraws'], 1)
        freq_max = max(context['freq'][1:] or [1])
        recent_max = max(context['recentFreq'][1:] or [1])
        pair_max = max((context.get('recentPairCounts') or context.get('pairCounts'))[1:] or [1])
        recent_window = max(context.get('recentDrawCount', 0), 1)
        long_window = max(context.get('totalDraws', 0), 1)
        ranking = self.score_set_candidate(candidate, normalized, {'normalizedRequest': normalized, 'sourceData': source_data, 'context': context, 'weights': weights})
        signals = []
        for number in candidate:
            last_seen = context['lastSeen'][number]
            gap = (context['totalDraws'] - 1 - last_seen) if last_seen >= 0 else context['totalDraws']
            long_rate = context['freq'][number] / long_window
            recent_rate = context['recentFreq'][number] / recent_window
            lift_raw = (recent_rate / long_rate) if long_rate > 0 else (2 if recent_rate > 0 else 1)
            overdue_ratio = min((gap + 1) / max(context['averageGap'][number] or 1, 1), 3)
            bayes_score = (context['freq'][number] + (context['recentFreq'][number] * 1.5) + 1) / (long_window + (recent_window * 1.5) + 2)
            signals.append({
                'number': number,
                'weight': round(weights[number], 6),
                'frequencyScore': round(context['freq'][number] / freq_max, 4),
                'recencyScore': round(context['recentFreq'][number] / recent_max, 4),
                'gapScore': round(gap / total_draws, 4),
                'pairScore': round(((context.get('recentPairCounts') or context.get('pairCounts'))[number] / pair_max), 4),
                'trendScore': round(clamp01((lift_raw - 0.5) / 1.5), 4),
                'overdueRatio': round(overdue_ratio, 4),
                'bayesScore': round(bayes_score, 4),
            })
        set_weight = sum(weights[number] for number in candidate)
        set_sum = AdvancedMonteCarlo.calculate_sum(candidate)
        ac = AdvancedMonteCarlo.calculate_ac(candidate)
        return {
            'strategyId': normalized['strategyId'],
            'evidenceTier': normalized['evidenceTier'],
            'numbers': candidate,
            'filtersPass': passes_filters(candidate, normalized.get('filters')),
            'summary': {
                'setWeight': round(set_weight, 6),
                'sum': set_sum,
                'ac': ac,
                'recommendationScore': round(ranking['score'] if ranking else 0, 6),
                'pairSynergy': round((ranking or {}).get('breakdown', {}).get('pairSynergy', 0), 6),
                'profileScore': round((ranking or {}).get('breakdown', {}).get('profileScore', 0), 6),
                'gapBalanceScore': round((ranking or {}).get('breakdown', {}).get('gapBalanceScore', 0), 6),
            },
            'adaptive': adaptive,
            'signals': signals,
        }

    def rank_ticket(self, my_numbers: Sequence[int], winning_numbers: Sequence[int], bonus: int) -> int:
        hit = 0
        has_bonus = False
        winning_set = set(int(number) for number in winning_numbers)
        for number in my_numbers:
            if int(number) in winning_set:
                hit += 1
            if int(number) == int(bonus):
                has_bonus = True
        if hit == 6:
            return 1
        if hit == 5 and has_bonus:
            return 2
        if hit == 5:
            return 3
        if hit == 4:
            return 4
        if hit == 3:
            return 5
        return 0

    def evaluate_ticket_set(self, ticket: Sequence[int], draw: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        options = options or {}
        if len(ticket) != 6 or not isinstance(draw, dict) or not isinstance(draw.get('numbers'), list):
            return {'rank': 0, 'prize': 0}
        rank = self.rank_ticket(ticket, draw['numbers'], int(draw.get('bonus', 0)))
        if rank < 1 or rank > 5:
            return {'rank': 0, 'prize': 0}
        payout_mode = resolve_payout_mode(options.get('payoutMode'))
        if rank == 1 and payout_mode == 'hybrid_dynamic_first':
            dynamic_prize = int(draw.get('first_prize') or draw.get('prize_amount') or 0)
            if dynamic_prize > 0:
                return {'rank': rank, 'prize': dynamic_prize}
        return {'rank': rank, 'prize': FIXED_PRIZE_BY_RANK.get(rank, 0)}


__all__ = ['StrategyEngine', 'FIXED_PRIZE_BY_RANK', 'resolve_payout_mode']
