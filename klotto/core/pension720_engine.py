from __future__ import annotations

import math
import random
from typing import Any, Callable, Dict, List, Optional, Sequence

from klotto.core.pension720_strategy_catalog import (
    create_default_pension720_strategy_request,
    get_pension720_strategy_meta,
    resolve_pension720_strategy_id,
)
from klotto.data.pension720 import normalize_pension720_draw


def clamp_int(value: Any, min_value: int, max_value: int, fallback: int) -> int:
    try:
        parsed = math.floor(float(value))
    except (TypeError, ValueError):
        return fallback
    return min(max_value, max(min_value, parsed))


def clamp_nullable_int(value: Any, min_value: int, max_value: int) -> Optional[int]:
    if value in (None, '', []):
        return None
    return clamp_int(value, min_value, max_value, min_value)


def xorshift32(seed: int) -> Callable[[], float]:
    state = int(seed) & 0xFFFFFFFF

    def next_value() -> float:
        nonlocal state
        state ^= (state << 13) & 0xFFFFFFFF
        state ^= (state >> 17) & 0xFFFFFFFF
        state ^= (state << 5) & 0xFFFFFFFF
        return float(state & 0xFFFFFFFF) / 4294967296.0

    return next_value


def weighted_pick(items: Sequence[Dict[str, Any]], rng: Callable[[], float]) -> Any:
    safe_items = [item for item in items if float(item.get('weight') or 0) > 0]
    total = sum(float(item.get('weight') or 0) for item in safe_items)
    if not safe_items or total <= 0:
        return items[0].get('value') if items else None
    cursor = rng() * total
    for item in safe_items:
        cursor -= float(item.get('weight') or 0)
        if cursor <= 0:
            return item.get('value')
    return safe_items[-1].get('value')


def normalize_pair(value: Any, min_value: int, max_value: int) -> Optional[List[int]]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        left = math.floor(float(value[0]))
        right = math.floor(float(value[1]))
    except (TypeError, ValueError):
        return None
    left = max(min_value, min(max_value, left))
    right = max(min_value, min(max_value, right))
    return [left, right] if left <= right else [right, left]


def normalize_groups(value: Any) -> Optional[List[int]]:
    if value in (None, '', []):
        return None
    source = value if isinstance(value, (list, tuple, set)) else str(value).replace(';', ',').split(',')
    groups = sorted({int(item) for item in source if str(item).strip().isdigit() and 1 <= int(item) <= 5})
    return groups or None


def normalize_digit(value: Any) -> Optional[int]:
    if value in (None, ''):
        return None
    try:
        digit = int(value)
    except (TypeError, ValueError):
        return None
    return digit if 0 <= digit <= 9 else None


def normalize_fixed_digits(value: Any) -> Optional[List[Optional[int]]]:
    if value in (None, '', []):
        return None
    out: List[Optional[int]] = [None] * 6
    found = False
    if isinstance(value, (list, tuple)):
        for pos, item in enumerate(list(value)[:6]):
            digit = normalize_digit(item)
            if digit is not None:
                out[pos] = digit
                found = True
        return out if found else None
    if isinstance(value, dict):
        has_zero_key = '0' in value or 0 in value
        for key, item in value.items():
            try:
                raw_pos = int(key)
            except (TypeError, ValueError):
                continue
            pos = raw_pos if has_zero_key else raw_pos - 1
            digit = normalize_digit(item)
            if 0 <= pos <= 5 and digit is not None:
                out[pos] = digit
                found = True
    return out if found else None


def normalize_excluded_digits(value: Any) -> Optional[List[List[int]]]:
    if value in (None, '', []):
        return None
    out: List[List[int]] = [[] for _ in range(6)]
    found = False

    def add_digit(pos: int, raw_digit: Any) -> None:
        nonlocal found
        digit = normalize_digit(raw_digit)
        if 0 <= pos <= 5 and digit is not None and digit not in out[pos]:
            out[pos].append(digit)
            found = True

    if isinstance(value, (list, tuple)):
        for pos, items in enumerate(list(value)[:6]):
            for item in (items if isinstance(items, (list, tuple, set)) else [items]):
                add_digit(pos, item)
        return [sorted(items) for items in out] if found else None

    if isinstance(value, dict):
        has_zero_key = '0' in value or 0 in value
        for key, raw_items in value.items():
            try:
                raw_pos = int(key)
            except (TypeError, ValueError):
                continue
            pos = raw_pos if has_zero_key else raw_pos - 1
            for item in (raw_items if isinstance(raw_items, (list, tuple, set)) else [raw_items]):
                add_digit(pos, item)
    return [sorted(items) for items in out] if found else None


def normalize_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'groups': normalize_groups(filters.get('groups')),
        'fixedDigits': normalize_fixed_digits(filters.get('fixedDigits')),
        'excludedDigitsByPosition': normalize_excluded_digits(filters.get('excludedDigitsByPosition')),
        'digitSumRange': normalize_pair(filters.get('digitSumRange'), 0, 54),
        'oddDigitRange': normalize_pair(filters.get('oddDigitRange'), 0, 6),
        'highDigitRange': normalize_pair(filters.get('highDigitRange'), 0, 6),
        'uniqueDigitMin': clamp_nullable_int(filters.get('uniqueDigitMin'), 1, 6),
        'maxSameDigit': clamp_nullable_int(filters.get('maxSameDigit'), 1, 6),
    }


def apply_profile_defaults(params: Dict[str, Any], profile: str = '') -> Dict[str, Any]:
    if profile == 'fast':
        return {**params, 'lookbackWindow': params.get('lookbackWindow') or 20, 'candidatePoolSize': params.get('candidatePoolSize') or 80}
    if profile == 'precise':
        return {**params, 'lookbackWindow': params.get('lookbackWindow') or 80, 'candidatePoolSize': params.get('candidatePoolSize') or 240}
    return {**params, 'lookbackWindow': params.get('lookbackWindow') or 40, 'candidatePoolSize': params.get('candidatePoolSize') or 140}


def normalize_pension720_request(raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    source = raw or {}
    profile = str(source.get('profile') or '') if source.get('profile') in {'fast', 'basic', 'precise'} else ''
    strategy_id = resolve_pension720_strategy_id(source.get('strategyId') or source.get('id') or profile or 'mixed_balance')
    defaults = create_default_pension720_strategy_request(strategy_id)
    params_value = source.get('params')
    filters_value = source.get('filters')
    raw_params: Dict[str, Any] = dict(params_value) if isinstance(params_value, dict) else {}
    raw_filters: Dict[str, Any] = dict(filters_value) if isinstance(filters_value, dict) else {}
    default_params: Dict[str, Any] = dict(defaults.get('params') or {})
    default_filters: Dict[str, Any] = dict(defaults.get('filters') or {})
    params = apply_profile_defaults(
        {**default_params, **raw_params, 'seed': source.get('seed', raw_params.get('seed', default_params.get('seed')))},
        profile,
    )
    seed = params.get('seed')
    normalized_seed = int(seed) if seed not in (None, '', []) and str(seed).lstrip('-').isdigit() and int(seed) > 0 else None
    return {
        'strategyId': strategy_id,
        'evidenceTier': defaults['evidenceTier'],
        'params': {
            'seed': normalized_seed,
            'lookbackWindow': clamp_int(params.get('lookbackWindow'), 1, 300, int(default_params['lookbackWindow'])),
            'candidatePoolSize': clamp_int(params.get('candidatePoolSize'), 20, 800, int(default_params['candidatePoolSize'])),
        },
        'filters': normalize_filters({**default_filters, **raw_filters}),
    }


def digit_frequency_meta(digits: Sequence[int]) -> Dict[str, int]:
    counts: Dict[int, int] = {}
    for digit in digits:
        counts[digit] = counts.get(digit, 0) + 1
    return {'uniqueCount': len(counts), 'maxSame': max(counts.values()) if counts else 0}


def count_adjacent_flow(digits: Sequence[int]) -> int:
    return sum(1 for index in range(1, len(digits)) if abs(int(digits[index]) - int(digits[index - 1])) == 1)


class Pension720Engine:
    def __init__(self, stats: Optional[Sequence[Dict[str, Any]]] = None):
        self.data = sorted(
            [draw for draw in (normalize_pension720_draw(row) for row in (stats or [])) if draw],
            key=lambda row: int(row['draw_no']),
        )
        self.analysis = self.build_analysis(self.data)

    def build_analysis(self, source_data: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
        rows = [row for row in (source_data or self.data) if row]
        group_stats = {
            group: {'group': group, 'count': 0, 'rawCount': 0, 'recentCount': 0, 'lastSeenDrawNo': 0, 'score': 1.0, 'gap': 0}
            for group in range(1, 6)
        }
        position_stats = [[1.0 for _ in range(10)] for _ in range(6)]
        bonus_position_stats = [[1.0 for _ in range(10)] for _ in range(6)]
        digit_gap_stats = [[0 for _ in range(10)] for _ in range(6)]
        latest_draw_no = int(rows[-1]['draw_no']) if rows else 0

        for index, draw in enumerate(rows):
            recency_weight = 1 + index / max(1, len(rows) - 1)
            group_row = group_stats[int(draw['group'])]
            group_row['rawCount'] += 1
            group_row['count'] = group_row['rawCount']
            group_row['lastSeenDrawNo'] = int(draw['draw_no'])
            group_row['score'] += recency_weight
            if index >= max(0, len(rows) - 20):
                group_row['recentCount'] += 1
                group_row['score'] += 0.8
            for pos, digit in enumerate(draw['digits']):
                position_stats[pos][int(digit)] += recency_weight
            for pos, digit in enumerate(draw['bonus_digits']):
                bonus_position_stats[pos][int(digit)] += recency_weight

        reversed_rows = list(reversed(rows))
        for pos in range(6):
            for digit in range(10):
                last_seen = next((int(draw['draw_no']) for draw in reversed_rows if int(draw['digits'][pos]) == digit), 0)
                digit_gap_stats[pos][digit] = latest_draw_no - last_seen if latest_draw_no and last_seen else len(rows)

        for group_row in group_stats.values():
            last_seen = int(group_row['lastSeenDrawNo'])
            gap = latest_draw_no - last_seen if latest_draw_no and last_seen else len(rows)
            group_row['gap'] = gap
            group_row['score'] += min(10, gap * 0.35)

        return {
            'latestDrawNo': latest_draw_no,
            'drawCount': len(rows),
            'groupStats': sorted(group_stats.values(), key=lambda row: float(row['score']), reverse=True),
            'positionStats': position_stats,
            'bonusPositionStats': bonus_position_stats,
            'digitGapStats': digit_gap_stats,
        }

    def get_analysis_for_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        lookback = int(request.get('params', {}).get('lookbackWindow') or len(self.data) or 1)
        return self.build_analysis(self.data[-max(1, lookback):])

    def create_rng(self, seed: Optional[int]) -> Callable[[], float]:
        if seed not in (None, '', []):
            try:
                return xorshift32(int(seed))
            except (TypeError, ValueError):
                return random.random
        return random.random

    def get_group_weight(self, item: Dict[str, Any], strategy_id: str) -> float:
        if strategy_id == 'random_baseline':
            return 1.0
        if strategy_id == 'group_rotation':
            return 1 + float(item['score']) * 0.35 + min(12, float(item['gap']) * 1.1)
        if strategy_id == 'gap_rebound':
            return 1 + float(item['score']) * 0.25 + min(10, float(item['gap']) * 0.8)
        return float(item['score'])

    def pick_group(self, rng: Callable[[], float], analysis: Dict[str, Any], request: Dict[str, Any]) -> int:
        allowed = set(request.get('filters', {}).get('groups') or [])
        items = [
            {'value': item['group'], 'weight': self.get_group_weight(item, request['strategyId'])}
            for item in analysis['groupStats']
            if not allowed or int(item['group']) in allowed
        ]
        fallback = [{'value': item['group'], 'weight': 1} for item in analysis['groupStats']]
        return int(weighted_pick(items or fallback, rng) or 1)

    def get_digit_weight(self, pos: int, digit: int, analysis: Dict[str, Any], request: Dict[str, Any]) -> float:
        strategy_id = request['strategyId']
        if strategy_id == 'random_baseline':
            return 1.0
        primary = float(analysis['positionStats'][pos][digit] or 1)
        bonus = float(analysis['bonusPositionStats'][pos][digit] or 1)
        gap = float(analysis['digitGapStats'][pos][digit] or 0)
        if strategy_id == 'position_hot':
            return 1 + primary * 1.65 + bonus * 0.2
        if strategy_id == 'trailing_match':
            return 1 + primary * (1.75 if pos >= 3 else 0.65) + bonus * (0.45 if pos >= 3 else 0.15)
        if strategy_id == 'group_rotation':
            return 1 + primary * 0.9 + bonus * 0.25 + min(5, gap * 0.08)
        if strategy_id == 'gap_rebound':
            return 1 + primary * 0.55 + min(12, gap * 0.8)
        if strategy_id == 'bonus_flow':
            return 1 + primary * 0.75 + bonus * 1.15
        if strategy_id == 'diversity':
            return 1 + primary * 0.85 + bonus * 0.15
        if strategy_id == 'consecutive_pattern':
            return 1 + primary * 0.95 + bonus * 0.2
        return 1 + primary + bonus * 0.35 + min(4, gap * 0.08)

    def get_exploration_rate(self, request: Dict[str, Any]) -> float:
        pool = int(request.get('params', {}).get('candidatePoolSize') or 140)
        if request.get('strategyId') == 'random_baseline':
            return 1.0
        if pool >= 220:
            return 0.18
        if pool <= 90:
            return 0.5
        return 0.32

    def pick_number(self, rng: Callable[[], float], analysis: Dict[str, Any], request: Dict[str, Any]) -> str:
        filters = request.get('filters') or {}
        fixed = filters.get('fixedDigits')
        excluded = filters.get('excludedDigitsByPosition')
        exploration = self.get_exploration_rate(request)
        digits: List[int] = []
        for pos in range(6):
            if isinstance(fixed, list) and fixed[pos] is not None:
                digits.append(int(fixed[pos]))
                continue
            excluded_set = set(excluded[pos] if isinstance(excluded, list) else [])
            previous = digits[pos - 1] if pos > 0 else None
            items = []
            for digit in range(10):
                weight = self.get_digit_weight(pos, digit, analysis, request)
                if request['strategyId'] == 'consecutive_pattern' and previous is not None and abs(previous - digit) == 1:
                    weight += 4
                items.append({'value': digit, 'weight': 0 if digit in excluded_set else 1 + weight * (1 - exploration) + rng() * exploration * 4})
            digits.append(int(weighted_pick(items, rng) or 0))
        return ''.join(str(digit) for digit in digits)

    def passes_filters(self, group: int, number: str, request: Dict[str, Any]) -> bool:
        filters = request.get('filters') or {}
        digits = [int(char) for char in str(number or '') if char.isdigit()]
        if len(digits) != 6:
            return False
        if filters.get('groups') and group not in filters['groups']:
            return False
        fixed = filters.get('fixedDigits')
        if isinstance(fixed, list):
            for pos in range(6):
                if fixed[pos] is not None and digits[pos] != int(fixed[pos]):
                    return False
        excluded = filters.get('excludedDigitsByPosition')
        if isinstance(excluded, list):
            for pos in range(6):
                if digits[pos] in set(excluded[pos] or []):
                    return False
        digit_sum = sum(digits)
        odd = sum(1 for digit in digits if digit % 2 != 0)
        high = sum(1 for digit in digits if digit >= 5)
        freq = digit_frequency_meta(digits)
        if filters.get('digitSumRange') and not (filters['digitSumRange'][0] <= digit_sum <= filters['digitSumRange'][1]):
            return False
        if filters.get('oddDigitRange') and not (filters['oddDigitRange'][0] <= odd <= filters['oddDigitRange'][1]):
            return False
        if filters.get('highDigitRange') and not (filters['highDigitRange'][0] <= high <= filters['highDigitRange'][1]):
            return False
        if filters.get('uniqueDigitMin') is not None and freq['uniqueCount'] < int(filters['uniqueDigitMin']):
            return False
        if filters.get('maxSameDigit') is not None and freq['maxSame'] > int(filters['maxSameDigit']):
            return False
        return True

    def score_candidate(self, group: int, number: str, analysis: Dict[str, Any], request: Dict[str, Any]) -> float:
        digits = [int(char) for char in str(number)]
        group_score = float(next((item['score'] for item in analysis['groupStats'] if int(item['group']) == group), 1))
        digit_score = 0.0
        for pos, digit in enumerate(digits):
            primary = float(analysis['positionStats'][pos][digit] or 1)
            bonus = float(analysis['bonusPositionStats'][pos][digit] or 1)
            gap = float(analysis['digitGapStats'][pos][digit] or 0)
            if request['strategyId'] == 'bonus_flow':
                digit_score += primary * 0.65 + bonus * 1.05
            elif request['strategyId'] == 'gap_rebound':
                digit_score += primary * 0.5 + min(12, gap * 0.85)
            elif request['strategyId'] == 'trailing_match':
                digit_score += primary * (1.6 if pos >= 3 else 0.7) + bonus * 0.3
            else:
                digit_score += primary + bonus * 0.35 + min(4, gap * 0.08)
        freq = digit_frequency_meta(digits)
        diversity_bonus = freq['uniqueCount'] * 3 - freq['maxSame'] * 2 if request['strategyId'] == 'diversity' else 0
        flow_bonus = count_adjacent_flow(digits) * 3 if request['strategyId'] == 'consecutive_pattern' else 0
        return round(group_score * 0.26 + digit_score * 0.74 + diversity_bonus + flow_bonus, 4)

    def explain_candidate(self, group: int, number: str, analysis: Dict[str, Any], request: Dict[str, Any]) -> List[str]:
        meta = get_pension720_strategy_meta(request['strategyId'])
        group_meta = next((item for item in analysis['groupStats'] if int(item['group']) == group), None)
        digits = [int(char) for char in str(number)]
        reasons = [str(meta['label'])]
        if group_meta:
            reasons.append(f"{group}조 빈도 {group_meta.get('rawCount', 0)}회, 최근 공백 {group_meta.get('gap', 0)}회")
        top_positions = []
        for pos, digit in enumerate(digits):
            weights = analysis['positionStats'][pos]
            top_digit = max(range(len(weights)), key=lambda index: weights[index])
            if top_digit == digit:
                top_positions.append(f'{pos + 1}번째 {digit}')
        if top_positions:
            reasons.append(f"자리별 강세: {', '.join(top_positions[:2])}")
        if request['strategyId'] == 'trailing_match':
            reasons.append('끝자리 당첨 구조를 더 크게 반영')
        if request['strategyId'] == 'bonus_flow':
            reasons.append('보너스 번호 자리 흐름을 보조 반영')
        if request['strategyId'] == 'gap_rebound':
            reasons.append('자리별 장기 미출현 숫자 보정')
        if request['strategyId'] == 'diversity':
            reasons.append(f"고유 숫자 {digit_frequency_meta(digits)['uniqueCount']}종")
        return reasons

    def recommend(self, options: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        raw_options = options or {}
        set_count = clamp_int(raw_options.get('setCount'), 1, 20, 5)
        request = normalize_pension720_request(raw_options.get('request') or raw_options.get('strategyRequest') or raw_options)
        rng = self.create_rng(raw_options.get('seed', request.get('params', {}).get('seed')))
        analysis = self.get_analysis_for_request(request)
        pool_size = max(set_count, int(request.get('params', {}).get('candidatePoolSize') or 140))
        candidates: Dict[str, Dict[str, Any]] = {}
        max_attempts = max(pool_size * 12, set_count * 80)
        for _index in range(max_attempts):
            if len(candidates) >= pool_size:
                break
            group = self.pick_group(rng, analysis, request)
            number = self.pick_number(rng, analysis, request)
            if not self.passes_filters(group, number, request):
                continue
            key = f'{group}|{number}'
            if key in candidates:
                continue
            allowed_groups = set(request.get('filters', {}).get('groups') or [])
            expansion_groups = [
                int(item['group'])
                for item in analysis['groupStats']
                if int(item['group']) != group and (not allowed_groups or int(item['group']) in allowed_groups)
            ]
            candidates[key] = {
                'group': group,
                'number': number,
                'digits': [int(char) for char in number],
                'score': self.score_candidate(group, number, analysis, request),
                'strategyId': request['strategyId'],
                'strategyLabel': get_pension720_strategy_meta(request['strategyId'])['label'],
                'expansionGroups': expansion_groups,
                'reasons': self.explain_candidate(group, number, analysis, request),
            }
        return sorted(candidates.values(), key=lambda row: float(row['score']), reverse=True)[:set_count]

    def get_summary(self) -> Dict[str, Any]:
        return {
            'latestDrawNo': self.analysis['latestDrawNo'],
            'drawCount': self.analysis['drawCount'],
            'topGroups': self.analysis['groupStats'][:5],
        }


__all__ = ['Pension720Engine', 'normalize_pension720_request']
