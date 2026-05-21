from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

BASE_PARAMS: Dict[str, Any] = {
    'seed': None,
    'lookbackWindow': 40,
    'candidatePoolSize': 140,
}

EMPTY_FILTERS: Dict[str, Any] = {
    'groups': None,
    'fixedDigits': None,
    'excludedDigitsByPosition': None,
    'digitSumRange': None,
    'oddDigitRange': None,
    'highDigitRange': None,
    'uniqueDigitMin': None,
    'maxSameDigit': None,
}

PENSION720_STRATEGY_ALIASES = {
    'basic': 'mixed_balance',
    'precise': 'position_hot',
    'fast': 'mixed_balance',
    'random': 'random_baseline',
    'mixed': 'mixed_balance',
    'position': 'position_hot',
    'trailing': 'trailing_match',
    'bonus': 'bonus_flow',
    'gap': 'gap_rebound',
    'group': 'group_rotation',
}


def _meta(
    strategy_id: str,
    label: str,
    tier: str,
    summary: str,
    *,
    description: str = '',
    experimental: bool = False,
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
        'defaultParams': {**BASE_PARAMS, **(default_params or {})},
        'defaultFilters': {**EMPTY_FILTERS, **(default_filters or {})},
    }


PENSION720_STRATEGY_CATALOG: Dict[str, Dict[str, Any]] = {
    'mixed_balance': _meta(
        'mixed_balance',
        '혼합 균형',
        'A',
        '조/자리/최근 흐름을 균형 반영',
        description='조별 빈도, 최근성, 공백, 자리별 숫자 강세, 보너스 흐름을 함께 보는 기본 연금복권 전략입니다.',
    ),
    'position_hot': _meta(
        'position_hot',
        '자리별 강세',
        'A',
        '각 자리에서 강한 숫자 우선',
        description='6자리 각각의 출현 빈도와 최근 흐름을 더 강하게 반영합니다.',
        default_params={'candidatePoolSize': 160},
    ),
    'trailing_match': _meta(
        'trailing_match',
        '끝자리 적중형',
        'B',
        '하위 등수와 연결되는 끝자리 집중',
        description='연금복권 당첨 구조상 중요한 뒤쪽 자리의 흐름을 더 크게 반영합니다.',
        default_params={'candidatePoolSize': 170},
    ),
    'group_rotation': _meta(
        'group_rotation',
        '조 로테이션',
        'B',
        '최근 공백이 긴 조를 보정',
        description='조별 최근 공백과 전체 출현 흐름을 함께 보고 조 선택을 넓힙니다.',
        default_params={'lookbackWindow': 60},
    ),
    'gap_rebound': _meta(
        'gap_rebound',
        '공백 반등',
        'B',
        '자리별 장기 미출현 숫자 보정',
        description='각 자리에서 오래 나오지 않은 숫자에 반등 가중치를 줍니다.',
        default_params={'lookbackWindow': 80, 'candidatePoolSize': 180},
    ),
    'bonus_flow': _meta(
        'bonus_flow',
        '보너스 흐름',
        'B',
        '보너스 번호 자리 흐름 보조 반영',
        description='1등 번호뿐 아니라 보너스 번호의 자리별 흐름을 더 많이 섞습니다.',
        default_params={'candidatePoolSize': 160},
    ),
    'random_baseline': _meta(
        'random_baseline',
        '완전 랜덤',
        'A',
        '조와 6자리 숫자를 균등 추출',
        description='과거 통계를 참고하지 않고 조와 여섯 자리를 균등하게 뽑습니다.',
        default_params={'candidatePoolSize': 80},
    ),
    'diversity': _meta(
        'diversity',
        '숫자 다양성',
        'C',
        '중복 숫자를 줄이고 분산 확보',
        description='[실험] 같은 숫자가 여러 번 반복되는 조합을 낮추고 다양한 숫자를 선호합니다.',
        experimental=True,
        default_params={'candidatePoolSize': 180},
        default_filters={'uniqueDigitMin': 4, 'maxSameDigit': 2},
    ),
    'consecutive_pattern': _meta(
        'consecutive_pattern',
        '연속 패턴',
        'C',
        '자리 사이 인접 흐름 탐색',
        description='[실험] 인접한 자리의 숫자 차이가 작게 이어지는 패턴을 후보로 더 탐색합니다.',
        experimental=True,
        default_params={'candidatePoolSize': 180},
    ),
}


def resolve_pension720_strategy_id(value: Optional[str]) -> str:
    if not value:
        return 'mixed_balance'
    raw = str(value or '').strip()
    if raw in PENSION720_STRATEGY_CATALOG:
        return raw
    return PENSION720_STRATEGY_ALIASES.get(raw, 'mixed_balance')


def get_pension720_strategy_meta(strategy_id: Optional[str]) -> Dict[str, Any]:
    resolved = resolve_pension720_strategy_id(strategy_id)
    return deepcopy(PENSION720_STRATEGY_CATALOG.get(resolved, PENSION720_STRATEGY_CATALOG['mixed_balance']))


def list_pension720_strategies(*, include_experimental: bool = False) -> List[Dict[str, Any]]:
    return [
        deepcopy(meta)
        for meta in PENSION720_STRATEGY_CATALOG.values()
        if include_experimental or not bool(meta.get('experimental'))
    ]


def create_default_pension720_strategy_request(strategy_id: str = 'mixed_balance') -> Dict[str, Any]:
    meta = get_pension720_strategy_meta(strategy_id)
    return {
        'strategyId': meta['id'],
        'evidenceTier': meta['tier'],
        'params': deepcopy(meta['defaultParams']),
        'filters': deepcopy(meta['defaultFilters']),
    }


__all__ = [
    'BASE_PARAMS',
    'EMPTY_FILTERS',
    'PENSION720_STRATEGY_ALIASES',
    'PENSION720_STRATEGY_CATALOG',
    'create_default_pension720_strategy_request',
    'get_pension720_strategy_meta',
    'list_pension720_strategies',
    'resolve_pension720_strategy_id',
]
