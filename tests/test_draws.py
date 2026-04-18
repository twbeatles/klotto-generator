from __future__ import annotations

import datetime as dt

from klotto.core.draws import KST, estimate_latest_draw, split_missing_draws


def test_estimate_latest_draw_respects_kst_saturday_cutoff():
    before_cutoff = dt.datetime(2026, 4, 18, 20, 59, tzinfo=KST)
    after_cutoff = dt.datetime(2026, 4, 18, 21, 1, tzinfo=KST)

    before = estimate_latest_draw(before_cutoff)
    after = estimate_latest_draw(after_cutoff)

    assert after == before + 1


def test_split_missing_draws_separates_recent_and_historical_gaps():
    result = split_missing_draws(
        {1, 2, 4, 7},
        8,
        current_draw=8,
        recent_window=2,
        allowed_missing={6},
    )

    assert result == {
        'all': [3, 5, 8],
        'recent': [8],
        'historical': [3, 5],
    }
