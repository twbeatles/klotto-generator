from __future__ import annotations

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