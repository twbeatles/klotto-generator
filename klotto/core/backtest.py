from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from klotto.config import APP_CONFIG
from klotto.core.strategy_engine import StrategyEngine, resolve_payout_mode
from klotto.data.models import BacktestComparison


@dataclass(slots=True)
class BacktestResult:
    summary: Dict[str, Any]
    comparisons: List[Dict[str, Any]]
    diagnostics: Dict[str, Any]



def _to_canonical_request(request: Dict[str, Any] | str | None) -> Dict[str, Any]:
    if isinstance(request, dict) and request.get('strategyId'):
        return request
    return {'strategyId': str(request or 'random_baseline'), 'params': {}, 'filters': {}}



def _create_report(strategy_id: str, payout_mode: str) -> Dict[str, Any]:
    return {
        'strategyId': strategy_id,
        'payoutMode': payout_mode,
        'draws': 0,
        'tickets': 0,
        'requestedTickets': 0,
        'generatedTickets': 0,
        'fillRate': 0.0,
        'cost': 0,
        'totalPrize': 0,
        'counts': {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
    }



def _summarize_report(report: Dict[str, Any]) -> Dict[str, Any]:
    win_count = sum(int(report['counts'].get(rank, 0)) for rank in (1, 2, 3, 4, 5))
    roi = ((report['totalPrize'] - report['cost']) / report['cost']) * 100 if report['cost'] > 0 else 0.0
    hit_rate = (win_count / report['tickets']) * 100 if report['tickets'] > 0 else 0.0
    fill_rate = (report['generatedTickets'] / report['requestedTickets']) * 100 if report['requestedTickets'] > 0 else 100.0
    comparison = BacktestComparison(
        strategy_id=report['strategyId'],
        payout_mode=report['payoutMode'],
        draws=report['draws'],
        tickets=report['tickets'],
        requested_tickets=report['requestedTickets'],
        generated_tickets=report['generatedTickets'],
        cost=report['cost'],
        total_prize=report['totalPrize'],
        counts={rank: int(report['counts'].get(rank, 0)) for rank in range(1, 6)},
        win_count=win_count,
        roi=round(roi, 4),
        hit_rate=round(hit_rate, 4),
        fill_rate=round(fill_rate, 4),
    )
    return comparison.to_dict()



def run_backtest(
    stats_data: Sequence[Dict[str, Any]],
    start_draw: int,
    end_draw: int,
    qty: int,
    strategy_requests: Optional[Iterable[Dict[str, Any] | str]] = None,
    payout_mode: str = 'hybrid_dynamic_first',
) -> BacktestResult:
    start = int(start_draw)
    end = int(end_draw)
    if start < 1 or end < 1 or start > end:
        raise ValueError('회차 범위가 올바르지 않습니다.')
    span = end - start + 1
    if span > int(APP_CONFIG['MAX_BACKTEST_SPAN']):
        raise ValueError(f"백테스트 범위는 최대 {APP_CONFIG['MAX_BACKTEST_SPAN']}회차까지 가능합니다.")

    all_stats = sorted([dict(draw) for draw in stats_data], key=lambda row: int(row.get('draw_no', 0)))
    draw_map = {int(draw.get('draw_no', 0)): draw for draw in all_stats}
    draw_index = {int(draw.get('draw_no', 0)): idx for idx, draw in enumerate(all_stats)}
    requests = [_to_canonical_request(item) for item in (strategy_requests or [{'strategyId': 'random_baseline'}])]
    normalization_engine = StrategyEngine(all_stats)
    strategy_draw_total = max(0, end - start + 1)
    total_draws = strategy_draw_total * len(requests)
    ticket_qty = max(1, int(qty or 1))

    processed_total = 0
    comparisons: List[Dict[str, Any]] = []

    for request in requests:
        normalized_request = normalization_engine.normalize_request(request)
        mode = resolve_payout_mode(normalized_request.get('params', {}).get('payoutMode') or payout_mode)
        report = _create_report(normalized_request['strategyId'], mode)

        for current_draw in range(start, end + 1):
            actual_result = draw_map.get(current_draw)
            index = draw_index.get(current_draw)
            history_data = all_stats[:index] if index is not None and index > 0 else []
            processed_total += 1
            if not actual_result:
                continue

            engine = StrategyEngine(history_data)
            tickets = engine.generate_multiple_sets(ticket_qty, request, {
                'sourceData': history_data,
                'normalizedRequest': normalized_request,
                'maxAttempts': ticket_qty * 120,
            })
            report['requestedTickets'] += ticket_qty
            report['generatedTickets'] += len(tickets)

            for ticket in tickets:
                evaluated = engine.evaluate_ticket_set(ticket, actual_result, {'payoutMode': mode})
                rank = int(evaluated.get('rank', 0))
                prize = int(evaluated.get('prize', 0))
                report['tickets'] += 1
                report['cost'] += 1000
                report['totalPrize'] += prize
                report['counts'][rank] = int(report['counts'].get(rank, 0)) + 1

            report['draws'] += 1
            report['fillRate'] = (report['generatedTickets'] / report['requestedTickets']) * 100 if report['requestedTickets'] > 0 else 100.0

        comparisons.append(_summarize_report(report))

    comparisons.sort(key=lambda row: float(row.get('roi', 0)), reverse=True)
    summary = comparisons[0] if comparisons else {}
    diagnostics = {
        'processedDraws': processed_total,
        'totalDraws': total_draws,
        'strategies': [row.get('strategyId') for row in comparisons],
    }
    return BacktestResult(summary=summary, comparisons=comparisons, diagnostics=diagnostics)


__all__ = ['BacktestResult', 'run_backtest']
