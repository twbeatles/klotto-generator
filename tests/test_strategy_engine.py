from __future__ import annotations

import datetime as dt

import pytest

from klotto.core.backtest import run_backtest
from klotto.core.draws import estimate_latest_draw
from klotto.core.strategy_engine import StrategyEngine
from klotto.qr_utils import parse_lotto_qr_url


SAMPLE_DRAWS = [
    {'draw_no': 1, 'numbers': [1, 2, 3, 4, 5, 6], 'bonus': 7, 'first_prize': 1000000000},
    {'draw_no': 2, 'numbers': [8, 9, 10, 11, 12, 13], 'bonus': 14, 'first_prize': 1000000000},
    {'draw_no': 3, 'numbers': [1, 8, 15, 22, 29, 36], 'bonus': 43, 'first_prize': 1000000000},
    {'draw_no': 4, 'numbers': [3, 11, 19, 27, 35, 43], 'bonus': 2, 'first_prize': 1000000000},
    {'draw_no': 5, 'numbers': [5, 10, 20, 25, 30, 40], 'bonus': 45, 'first_prize': 1000000000},
    {'draw_no': 6, 'numbers': [7, 14, 21, 28, 35, 42], 'bonus': 1, 'first_prize': 1000000000},
    {'draw_no': 7, 'numbers': [4, 12, 18, 24, 33, 41], 'bonus': 6, 'first_prize': 1000000000},
    {'draw_no': 8, 'numbers': [2, 16, 23, 31, 38, 44], 'bonus': 9, 'first_prize': 1000000000},
    {'draw_no': 9, 'numbers': [6, 13, 17, 26, 34, 45], 'bonus': 8, 'first_prize': 1000000000},
    {'draw_no': 10, 'numbers': [1, 9, 18, 27, 36, 45], 'bonus': 11, 'first_prize': 1000000000},
    {'draw_no': 11, 'numbers': [2, 11, 20, 29, 38, 44], 'bonus': 5, 'first_prize': 1000000000},
    {'draw_no': 12, 'numbers': [7, 15, 22, 31, 37, 43], 'bonus': 3, 'first_prize': 1000000000},
]


def test_normalize_request_alias_and_bounds():
    engine = StrategyEngine(SAMPLE_DRAWS)
    request = engine.normalize_request({
        'strategyId': 'random',
        'params': {'simulationCount': 999999, 'lookbackWindow': 1, 'wheelPoolSize': 99, 'wheelGuarantee': 99, 'seed': '77'},
        'filters': {'maxConsecutivePairs': 99},
    })
    assert request['strategyId'] == 'random_baseline'
    assert request['params']['simulationCount'] == 20000
    assert request['params']['lookbackWindow'] == 5
    assert request['params']['wheelPoolSize'] == 20
    assert request['params']['wheelGuarantee'] == 5
    assert request['params']['seed'] == 77
    assert request['filters']['maxConsecutivePairs'] == 5



def test_generation_is_reproducible_with_seed():
    engine = StrategyEngine(SAMPLE_DRAWS)
    request = {
        'strategyId': 'ensemble_weighted',
        'params': {'seed': 2026, 'simulationCount': 1500, 'lookbackWindow': 10},
        'filters': {'maxConsecutivePairs': 2},
    }
    first = engine.generate_multiple_sets(5, request)
    second = engine.generate_multiple_sets(5, request)
    assert first == second
    assert len(first) == 5



def test_auto_strategy_reports_adaptive_diagnostics():
    engine = StrategyEngine(SAMPLE_DRAWS)
    result = engine.recommend_from_simulation({
        'strategyId': 'auto_recent_top',
        'params': {'seed': 13, 'simulationCount': 1500, 'lookbackWindow': 10},
        'filters': {},
    }, {'setCount': 3})
    diagnostics = result['simulation']['diagnostics']
    assert result['sets']
    assert diagnostics['adaptive'] is not None
    assert diagnostics['effectiveAdaptiveWindow'] is not None



def test_backtest_returns_comparisons():
    result = run_backtest(
        SAMPLE_DRAWS,
        start_draw=6,
        end_draw=12,
        qty=3,
        strategy_requests=[
            {'strategyId': 'ensemble_weighted', 'params': {'seed': 5, 'simulationCount': 1200, 'lookbackWindow': 8}, 'filters': {}},
            {'strategyId': 'hot_frequency', 'params': {'seed': 5, 'simulationCount': 1200, 'lookbackWindow': 8}, 'filters': {}},
        ],
    )
    assert len(result.comparisons) == 2
    assert result.summary['strategyId'] in {'ensemble_weighted', 'hot_frequency'}
    assert result.diagnostics['processedDraws'] > 0


def test_estimate_latest_draw_uses_kst_release_cutoff():
    before_release = estimate_latest_draw(dt.datetime(2026, 4, 25, 21, 59))
    at_release = estimate_latest_draw(dt.datetime(2026, 4, 25, 22, 0))
    next_day = estimate_latest_draw(dt.datetime(2026, 4, 26, 9, 0))

    assert at_release == before_release + 1
    assert next_day == at_release


def test_parse_lotto_qr_url_validates_draw_and_numbers():
    payload = parse_lotto_qr_url('https://m.dhlottery.co.kr/?v=123m010203040506n070809101112')
    assert payload == {
        'draw_no': 123,
        'sets': [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]],
    }

    with pytest.raises(ValueError):
        parse_lotto_qr_url('https://m.dhlottery.co.kr/?v=0m010203040506')

    with pytest.raises(ValueError):
        parse_lotto_qr_url('https://m.dhlottery.co.kr/?v=123m010101010101')

    with pytest.raises(ValueError):
        parse_lotto_qr_url('https://m.dhlottery.co.kr/?v=123m004647484950')
