from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

BASE_PARAMS: Dict[str, Any] = {
    'simulationCount': 5000,
    'lookbackWindow': 20,
    'wheelPoolSize': None,
    'wheelGuarantee': None,
    'seed': None,
    'payoutMode': 'hybrid_dynamic_first',
}

EMPTY_FILTERS: Dict[str, Any] = {
    'oddEven': None,
    'highLow': None,
    'sumRange': None,
    'acRange': None,
    'maxConsecutivePairs': None,
    'endDigitUniqueMin': None,
}

LEGACY_STRATEGY_ALIASES = {
    'ensemble': 'ensemble_weighted',
    'statistical': 'stat_ac_sum',
    'balance': 'balance_oe_hl',
    'cold': 'cold_frequency',
    'hot': 'hot_frequency',
    'random': 'random_baseline',
}

AUTO_STRATEGY_IDS = {'auto_recent_top', 'auto_ensemble_top3'}


def _meta(
    strategy_id: str,
    label: str,
    tier: str,
    summary: str,
    *,
    description: str = '',
    experimental: bool = False,
    scopes: Optional[List[str]] = None,
    default_params: Optional[Dict[str, Any]] = None,
    default_filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        'id': strategy_id,
        'label': label,
        'tier': tier,
        'experimental': experimental,
        'summary': summary,
        'description': description,
        'scopes': scopes,
        'defaultParams': {**BASE_PARAMS, **(default_params or {})},
        'defaultFilters': {**EMPTY_FILTERS, **(default_filters or {})},
    }


STRATEGY_CATALOG: Dict[str, Dict[str, Any]] = {
    'random_baseline': _meta('random_baseline', '완전 랜덤', 'A', '균등 확률 비복원 추출'),
    'ensemble_weighted': _meta('ensemble_weighted', '앙상블 가중치', 'A', '빈도/최근/공백 신호를 혼합'),
    'consensus_portfolio': _meta('consensus_portfolio', '컨센서스 포트폴리오', 'A', '강한 신호의 교집합을 다시 선별', default_params={'simulationCount': 6500}),
    'bayesian_smooth': _meta('bayesian_smooth', '베이지안 스무딩', 'A', '과적합을 줄인 확률형 추정', default_params={'simulationCount': 6000}),
    'momentum_recent': _meta('momentum_recent', '모멘텀 추세', 'B', '최근 상승세 번호에 가속도 부여', default_params={'lookbackWindow': 24}),
    'mean_reversion_cycle': _meta('mean_reversion_cycle', '평균회귀 사이클', 'B', '예상 공백 대비 늦어진 번호를 보정', default_params={'lookbackWindow': 28}),
    'auto_recent_top': _meta('auto_recent_top', '자동 선택(최근 상위 1개)', 'A', '최근 N회 기준 최상위 전략 자동 선택', scopes=['ai'], default_params={'simulationCount': 5500, 'lookbackWindow': 20}),
    'auto_ensemble_top3': _meta('auto_ensemble_top3', '자동 앙상블(상위 3개)', 'A', '최근 상위 3개 전략을 자동 혼합', scopes=['ai'], default_params={'simulationCount': 6000, 'lookbackWindow': 20}),
    'hot_frequency': _meta('hot_frequency', '핫 빈도 추종', 'B', '빈출 번호 우선'),
    'cold_frequency': _meta('cold_frequency', '콜드 반등', 'B', '저빈도/장기 미출현 보정'),
    'recency_gap': _meta('recency_gap', '최근성-갭', 'A', '최근성과 미출현 길이를 함께 반영'),
    'balance_oe_hl': _meta('balance_oe_hl', '홀짝/고저 밸런스', 'B', '균형형 필터 중심', default_filters={'oddEven': [2, 4], 'highLow': [2, 4]}),
    'stat_ac_sum': _meta('stat_ac_sum', '정밀 통계(복잡도/합계)', 'B', '복잡도 지수와 합계 구간 기반 필터', default_params={'simulationCount': 8000}, default_filters={'sumRange': [100, 175], 'acRange': [7, 10]}),
    'pair_cooccurrence': _meta('pair_cooccurrence', '공출현 페어', 'B', '동시 출현 페어 빈도 가중'),
    'adjacency_bias': _meta('adjacency_bias', '인접수 편향', 'B', '직전 회차 인접 번호 가중'),
    'zone_split_3band': _meta('zone_split_3band', '3구간 분할', 'B', '1-15/16-30/31-45 구간 균형'),
    'wheel_full': _meta('wheel_full', '휠링(풀)', 'A', '후보군 기반 조합 확장', default_params={'wheelPoolSize': 10, 'wheelGuarantee': 4}),
    'wheel_reduced_t3': _meta('wheel_reduced_t3', '휠링(축약 3단계)', 'B', '소수 티켓 중심 축약 휠', default_params={'wheelPoolSize': 9, 'wheelGuarantee': 3}),
    'skip_hit_weighted': _meta('skip_hit_weighted', '결번/출현 가중', 'B', '결번-출현 리듬 기반', experimental=True, default_params={'simulationCount': 7000}),
    'last_digit_balance': _meta('last_digit_balance', '끝수 균형', 'C', '끝수 분산 중심', experimental=True, default_params={'simulationCount': 7000}, default_filters={'endDigitUniqueMin': 4}),
    'delta_gap_pattern': _meta('delta_gap_pattern', '간격 패턴', 'C', '번호 간 간격 분포 근사', experimental=True, default_params={'simulationCount': 7000}),
    'carryover_repeat_control': _meta('carryover_repeat_control', '이월 반복 제어', 'C', '직전 회차 반복 수 조정', experimental=True, default_params={'simulationCount': 7000}, default_filters={'maxConsecutivePairs': 2}),
}


def resolve_strategy_id(value: Optional[str]) -> str:
    if not value:
        return 'ensemble_weighted'
    if value in STRATEGY_CATALOG:
        return value
    return LEGACY_STRATEGY_ALIASES.get(value, 'ensemble_weighted')



def get_strategy_meta(strategy_id: Optional[str]) -> Dict[str, Any]:
    resolved = resolve_strategy_id(strategy_id)
    return STRATEGY_CATALOG.get(resolved, STRATEGY_CATALOG['ensemble_weighted'])



def is_auto_strategy_id(value: Optional[str]) -> bool:
    return resolve_strategy_id(value) in AUTO_STRATEGY_IDS



def list_strategies(*, include_experimental: bool = False, scope: Optional[str] = None) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for meta in STRATEGY_CATALOG.values():
        if meta.get('experimental') and not include_experimental:
            continue
        scopes = meta.get('scopes') or []
        if scope and scopes and scope not in scopes:
            continue
        items.append(deepcopy(meta))
    return items



def create_default_strategy_request(strategy_id: str = 'ensemble_weighted') -> Dict[str, Any]:
    meta = get_strategy_meta(strategy_id)
    return {
        'strategyId': meta['id'],
        'evidenceTier': meta['tier'],
        'params': deepcopy(meta['defaultParams']),
        'filters': deepcopy(meta['defaultFilters']),
    }


__all__ = [
    'AUTO_STRATEGY_IDS',
    'BASE_PARAMS',
    'EMPTY_FILTERS',
    'LEGACY_STRATEGY_ALIASES',
    'STRATEGY_CATALOG',
    'create_default_strategy_request',
    'get_strategy_meta',
    'is_auto_strategy_id',
    'list_strategies',
    'resolve_strategy_id',
]
