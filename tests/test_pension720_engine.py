from __future__ import annotations

from klotto.core.pension720_engine import Pension720Engine
from klotto.data.pension720 import (
    build_pension720_ticket_csv,
    evaluate_pension720_ticket,
    normalize_pension720_draw,
    normalize_pension720_stats,
    resolve_pension720_ticket_check,
)


def _sample_stats() -> list[dict]:
    return [
        {
            'draw_no': 3,
            'date': '2026-05-14',
            'group': 2,
            'digits': [5, 3, 7, 5, 3, 0],
            'number': '537530',
            'bonus_digits': [3, 5, 8, 1, 2, 7],
            'bonus_number': '358127',
        },
        {
            'draw_no': 2,
            'date': '2026-05-07',
            'group': 2,
            'digits': [0, 6, 0, 7, 2, 7],
            'number': '060727',
            'bonus_digits': [2, 9, 3, 1, 6, 0],
            'bonus_number': '293160',
        },
        {
            'draw_no': 1,
            'date': '2026-04-30',
            'group': 5,
            'digits': [7, 2, 6, 4, 9, 3],
            'number': '726493',
            'bonus_digits': [8, 8, 2, 0, 3, 3],
            'bonus_number': '882033',
        },
    ]


def test_pension720_draw_normalization_preserves_leading_zeroes():
    normalized = normalize_pension720_draw(
        {
            'psltEpsd': 314,
            'psltRflYmd': '20260507',
            'wnBndNo': '2',
            'wnRnkVl': '060727',
            'bnsRnkVl': '293160',
        }
    )

    assert normalized is not None
    assert normalized['draw_no'] == 314
    assert normalized['date'] == '2026-05-07'
    assert normalized['group'] == 2
    assert normalized['number'] == '060727'
    assert normalized['digits'] == [0, 6, 0, 7, 2, 7]
    assert normalize_pension720_draw({**normalized, 'group': 6}) is None


def test_pension720_seeded_recommendation_and_filters_are_stable():
    engine = Pension720Engine(_sample_stats())
    request = {
        'strategyId': 'trailing_match',
        'params': {'seed': 720, 'lookbackWindow': 3, 'candidatePoolSize': 80},
        'filters': {
            'groups': [2],
            'fixedDigits': [0, None, None, None, None, None],
            'excludedDigitsByPosition': [[], [9], [], [], [], []],
            'digitSumRange': [5, 40],
            'uniqueDigitMin': 2,
            'maxSameDigit': 3,
        },
    }

    first = engine.recommend({'setCount': 2, 'request': request})
    second = engine.recommend({'setCount': 2, 'request': request})

    assert first == second
    assert len(first) == 2
    for row in first:
        assert row['group'] == 2
        assert row['number'].startswith('0')
        assert row['digits'][1] != 9
        assert row['strategyId'] == 'trailing_match'
        assert row['expansionGroups'] == []


def test_pension720_latest_check_contract_matches_webapp_rules():
    draw = {
        'draw_no': 315,
        'date': '2026-05-14',
        'group': 2,
        'number': '537530',
        'bonus_number': '358127',
    }
    cases = [
        ({'group': 2, 'number': '537530'}, 1, 'primary', 7),
        ({'group': 5, 'number': '537530'}, 2, 'primary', 6),
        ({'group': 1, 'number': '358127'}, 'bonus', 'bonus', 6),
        ({'group': 1, 'number': '037530'}, 3, 'primary', 5),
        ({'group': 1, 'number': '007530'}, 4, 'primary', 4),
        ({'group': 1, 'number': '000530'}, 5, 'primary', 3),
        ({'group': 1, 'number': '000030'}, 6, 'primary', 2),
        ({'group': 1, 'number': '000000'}, 7, 'primary', 1),
        ({'group': 1, 'number': '123456'}, 0, 'none', 0),
    ]

    for ticket, rank, match_type, trailing in cases:
        result = evaluate_pension720_ticket(ticket, draw)
        assert result is not None
        assert result['rank'] == rank
        assert result['matchType'] == match_type
        assert result['trailingMatches'] == trailing


def test_pension720_target_aware_check_and_csv_formula_escape():
    rows = normalize_pension720_stats(
        [
            {'draw_no': 315, 'date': '2026-05-14', 'group': 2, 'number': '537530', 'bonus_number': '358127'},
            {'draw_no': 314, 'date': '2026-05-07', 'group': 1, 'number': '111111', 'bonus_number': '222222'},
        ]
    )

    target = resolve_pension720_ticket_check({'group': 1, 'number': '111111', 'targetDrawNo': 314}, rows)
    future = resolve_pension720_ticket_check({'group': 1, 'number': '123456', 'targetDrawNo': 316}, rows)
    missing = resolve_pension720_ticket_check({'group': 1, 'number': '123456', 'targetDrawNo': 313}, rows)
    reference = resolve_pension720_ticket_check({'group': 2, 'number': '537530'}, rows)

    assert target['status'] == 'target'
    assert target['result']['rank'] == 1
    assert future['status'] == 'pending'
    assert future['result'] is None
    assert missing['status'] == 'missing'
    assert reference['status'] == 'reference'
    assert reference['result']['rank'] == 1

    csv_text = build_pension720_ticket_csv(
        [
            {
                'group': 2,
                'number': '060727',
                'targetDrawNo': 316,
                'campaignId': 'campaign',
                'source': 'recommendation',
                'score': 1.5,
                'memo': '=1+1',
                'createdAt': '2026-05-19T00:00:00',
            }
        ]
    )
    assert 'memo' in csv_text
    assert "'=1+1" in csv_text
    assert ',=1+1,' not in csv_text
