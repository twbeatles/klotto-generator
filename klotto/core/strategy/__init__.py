"""Strategy engine package."""

from .constants import ADAPTIVE_SOURCE_STRATEGIES, FIXED_PRIZE_BY_RANK
from .engine import StrategyEngine
from .utils import (
    clamp,
    clamp01,
    compute_delta_affinity,
    count_overlap,
    create_adaptive_key,
    create_matrix,
    get_numbers,
    get_recommendation_mix,
    normalize_around,
    normalize_ratio,
    normalize_weights,
    pick_diverse_candidates,
    resolve_payout_mode,
    score_by_distance,
    sort_candidate,
    summarize_series,
    xorshift32,
)

__all__ = [
    'ADAPTIVE_SOURCE_STRATEGIES',
    'FIXED_PRIZE_BY_RANK',
    'StrategyEngine',
    'clamp',
    'clamp01',
    'compute_delta_affinity',
    'count_overlap',
    'create_adaptive_key',
    'create_matrix',
    'get_numbers',
    'get_recommendation_mix',
    'normalize_around',
    'normalize_ratio',
    'normalize_weights',
    'pick_diverse_candidates',
    'resolve_payout_mode',
    'score_by_distance',
    'sort_candidate',
    'summarize_series',
    'xorshift32',
]
