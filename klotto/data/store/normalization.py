from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, cast
from uuid import uuid4

from klotto.config import APP_CONFIG
from klotto.core.lotto_rules import calculate_rank, normalize_numbers, normalize_positive_int, safe_int
from klotto.core.pension720_engine import normalize_pension720_request
from klotto.core.pension720_strategy_catalog import create_default_pension720_strategy_request
from klotto.core.strategy_catalog import create_default_strategy_request
from klotto.core.strategy_filters import sanitize_filters
from klotto.data.pension720 import normalize_six_digits
from klotto.data.store_utils import load_json_data, save_json_atomic
from klotto.logging import logger
from klotto.net.http import normalize_proxy_url
from klotto.data.store.api import StoreAPI


class NormalizationMixin(StoreAPI):
    def normalize_ticket_quantity(self, value: Any) -> int:
        quantity = max(1, safe_int(value, default=1))
        return quantity if quantity > 0 else 1

    def normalize_generator_options(self, raw: Any) -> Dict[str, Any]:
        defaults = self.create_default_state()['generatorOptions']
        options = raw if isinstance(raw, dict) else {}
        return {
            'num_sets': self.clamp_int(options.get('num_sets'), 1, int(APP_CONFIG['MAX_SETS']), int(defaults['num_sets'])),
            'fixed_nums': str(options.get('fixed_nums') or '')[:500],
            'exclude_nums': str(options.get('exclude_nums') or '')[:500],
            'check_consecutive': self.normalize_bool(options.get('check_consecutive'), bool(defaults['check_consecutive'])),
            'consecutive_limit': self.clamp_int(options.get('consecutive_limit'), 0, 5, int(defaults['consecutive_limit'])),
        }

    def get_generator_options(self) -> Dict[str, Any]:
        return self.normalize_generator_options(self.state.get('generatorOptions') or {})

    def update_generator_options(self, **updates: Any) -> Dict[str, Any]:
        self.state['generatorOptions'] = self.normalize_generator_options({**self.get_generator_options(), **updates})
        self.save()
        return dict(self.state['generatorOptions'])

    def normalize_alert_prefs(self, raw: Any) -> Dict[str, bool]:
        prefs = raw if isinstance(raw, dict) else {}
        return {
            'enableInApp': bool(prefs.get('enableInApp', True)),
            'enableSystemNotification': bool(prefs.get('enableSystemNotification', False)),
            'notifyOnNewResult': bool(prefs.get('notifyOnNewResult', True)),
        }

    def get_alert_prefs(self) -> Dict[str, bool]:
        return self.normalize_alert_prefs(self.state.get('alertPrefs') or {})

    def update_alert_prefs(self, **updates: Any) -> Dict[str, bool]:
        self.state['alertPrefs'] = self.normalize_alert_prefs({**self.get_alert_prefs(), **updates})
        self.save()
        return dict(self.state['alertPrefs'])

    def set_proxy_url(self, value: Any) -> str:
        normalized = normalize_proxy_url(value)[:500]
        self.state['proxyUrl'] = normalized
        self.save()
        return normalized

    def get_strategy_presets(self, scope: str) -> List[Dict[str, Any]]:
        return [dict(item) for item in self.state['strategyPresets'] if item.get('scope') == scope]

    def get_ticket_quantity(self, ticket: Dict[str, Any]) -> int:
        return self.normalize_ticket_quantity(ticket.get('quantity'))

    def get_total_ticket_count(self, tickets: Optional[Sequence[Dict[str, Any]]] = None) -> int:
        return sum(self.get_ticket_quantity(ticket) for ticket in (tickets or self.state['ticketBook']))

    def clamp_int(self, value: Any, min_value: int, max_value: int, fallback: int) -> int:
        parsed = safe_int(value, fallback)
        return max(min_value, min(max_value, parsed))

    def normalize_optional_int(self, value: Any, min_value: int, max_value: int, fallback: Optional[int]) -> Optional[int]:
        if value in (None, '', []):
            return fallback
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return fallback
        if parsed <= 0:
            return fallback
        return max(min_value, min(max_value, parsed))

    def normalize_bool(self, value: Any, fallback: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {'1', 'true', 'yes', 'y', 'on'}:
                return True
            if lowered in {'0', 'false', 'no', 'n', 'off'}:
                return False
        return fallback

    def normalize_strategy_request(self, raw: Any) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            return create_default_strategy_request('ensemble_weighted')
        strategy_id = str(raw.get('strategyId') or 'ensemble_weighted')
        base = create_default_strategy_request(strategy_id)
        base_params_value = base.get('params')
        base_params = cast(Dict[str, Any], base_params_value) if isinstance(base_params_value, dict) else {}
        base_filters_value = base.get('filters')
        base_filters = cast(Dict[str, Any], base_filters_value) if isinstance(base_filters_value, dict) else {}
        raw_params_value = raw.get('params')
        raw_params = cast(Dict[str, Any], raw_params_value) if isinstance(raw_params_value, dict) else {}
        raw_filters_value = raw.get('filters')
        raw_filters = cast(Dict[str, Any], raw_filters_value) if isinstance(raw_filters_value, dict) else {}
        incoming_params = {**base_params, **raw_params}
        incoming_filters = sanitize_filters({**base_filters, **raw_filters})
        params = {
            'simulationCount': self.clamp_int(incoming_params.get('simulationCount'), 1000, 20000, int(base_params.get('simulationCount') or 5000)),
            'lookbackWindow': self.clamp_int(incoming_params.get('lookbackWindow'), 5, 120, int(base_params.get('lookbackWindow') or 20)),
            'wheelPoolSize': self.normalize_optional_int(incoming_params.get('wheelPoolSize'), 7, 20, base_params.get('wheelPoolSize')),
            'wheelGuarantee': self.normalize_optional_int(incoming_params.get('wheelGuarantee'), 2, 5, base_params.get('wheelGuarantee')),
            'seed': self.normalize_seed(incoming_params.get('seed')),
            'payoutMode': incoming_params.get('payoutMode') if incoming_params.get('payoutMode') in {'hybrid_dynamic_first', 'fast_fixed'} else base_params.get('payoutMode', 'hybrid_dynamic_first'),
        }
        filters = {
            'oddEven': self.normalize_filter_pair(incoming_filters.get('oddEven'), 0, 6),
            'highLow': self.normalize_filter_pair(incoming_filters.get('highLow'), 0, 6),
            'sumRange': self.normalize_filter_pair(incoming_filters.get('sumRange'), 0, 300),
            'acRange': self.normalize_filter_pair(incoming_filters.get('acRange'), 0, 20),
            'maxConsecutivePairs': None if incoming_filters.get('maxConsecutivePairs') is None else self.clamp_int(incoming_filters.get('maxConsecutivePairs'), 0, 5, 2),
            'endDigitUniqueMin': None if incoming_filters.get('endDigitUniqueMin') is None else self.clamp_int(incoming_filters.get('endDigitUniqueMin'), 1, 6, 4),
        }
        return {
            'strategyId': str(base['strategyId']),
            'evidenceTier': str(raw.get('evidenceTier') or base['evidenceTier']),
            'params': params,
            'filters': filters,
        }

    def normalize_pension720_strategy_request(self, raw: Any) -> Dict[str, Any]:
        return normalize_pension720_request(raw if isinstance(raw, dict) else create_default_pension720_strategy_request('mixed_balance'))

    def normalize_filter_pair(self, value: Any, min_value: int, max_value: int) -> Optional[List[int]]:
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            return None
        left = self.clamp_int(value[0], min_value, max_value, min_value)
        right = self.clamp_int(value[1], min_value, max_value, max_value)
        return [left, right] if left <= right else [right, left]

    def normalize_seed(self, value: Any) -> Optional[int]:
        if value in (None, '', []):
            return None
        text = str(value).strip()
        if not text.lstrip('-').isdigit():
            return None
        return safe_int(text, 0)

    def normalize_strategy_preset(self, raw: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict):
            return None
        scope = str(raw.get('scope') or '').strip()
        name = str(raw.get('name') or '').strip()
        if scope not in {'generator', 'ai', 'backtest', 'pension720'} or not name:
            return None
        request = raw.get('request') or raw.get('strategyRequest') or {}
        normalized_request = self.normalize_pension720_strategy_request(request) if scope == 'pension720' else self.normalize_strategy_request(request)
        return {
            'id': str(raw.get('id') or self.create_id('preset')),
            'scope': scope,
            'name': name[:80],
            'description': str(raw.get('description') or '')[:200],
            'request': normalized_request,
            'createdAt': str(raw.get('createdAt') or dt.datetime.now().isoformat()),
            'updatedAt': str(raw.get('updatedAt') or dt.datetime.now().isoformat()),
        }

    def normalize_pension720_data_health(self, raw: Any) -> Dict[str, Any]:
        defaults = self.create_default_state()['pension720DataHealth']
        source = raw if isinstance(raw, dict) else {}
        availability = source.get('availability') if source.get('availability') in {'full', 'none'} else defaults['availability']
        data_source = source.get('source') if source.get('source') in {'static', 'official', 'official_cache', 'none'} else defaults['source']
        return {
            'availability': availability,
            'source': data_source,
            'latestDrawNo': max(0, safe_int(source.get('latestDrawNo'), default=0)),
            'message': str(source.get('message') or defaults['message'])[:240],
            'updatedAt': str(source.get('updatedAt') or defaults['updatedAt']),
        }

    def normalize_ticket_entry(self, raw: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict):
            return None
        numbers = normalize_numbers(raw.get('numbers'))
        if not numbers:
            return None
        target_draw_no = normalize_positive_int(raw.get('targetDrawNo'))
        if target_draw_no is None:
            return None
        source = str(raw.get('source') or 'import')
        if source not in {'generator', 'ai', 'import'}:
            source = 'import'
        checked = raw.get('checked') if isinstance(raw.get('checked'), dict) else None
        normalized_checked = None
        if checked:
            checked_draw = normalize_positive_int(checked.get('drawNo'))
            checked_rank = max(0, min(5, safe_int(checked.get('rank'), default=0)))
            if checked_draw is not None and 0 <= checked_rank <= 5:
                normalized_checked = {
                    'drawNo': checked_draw,
                    'rank': checked_rank,
                    'checkedAt': str(checked.get('checkedAt') or dt.datetime.now().isoformat()),
                }
        ticket = {
            'id': str(raw.get('id') or self.create_id('ticket')),
            'numbers': numbers,
            'targetDrawNo': target_draw_no,
            'source': source,
            'quantity': self.normalize_ticket_quantity(raw.get('quantity')),
            'campaignId': str(raw.get('campaignId') or '')[:120],
            'strategyRequest': self.normalize_strategy_request(raw.get('strategyRequest') or create_default_strategy_request('ensemble_weighted')) if raw.get('strategyRequest') else None,
            'memo': str(raw.get('memo') or '')[:200],
            'createdAt': str(raw.get('createdAt') or dt.datetime.now().isoformat()),
            'checked': normalized_checked,
        }
        ticket['_dedupeKey'] = self.build_ticket_key(ticket)
        return ticket

    def normalize_campaign_entry(self, raw: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict):
            return None
        start_draw_no = normalize_positive_int(raw.get('startDrawNo'))
        weeks = normalize_positive_int(raw.get('weeks'))
        sets_per_week = normalize_positive_int(raw.get('setsPerWeek'))
        if start_draw_no is None or weeks is None or sets_per_week is None:
            return None
        if weeks > int(APP_CONFIG['MAX_CAMPAIGN_WEEKS']) or sets_per_week > int(APP_CONFIG['MAX_CAMPAIGN_SETS_PER_WEEK']):
            return None
        if weeks * sets_per_week > int(APP_CONFIG['MAX_CAMPAIGN_TOTAL_TICKETS']):
            return None
        return {
            'id': str(raw.get('id') or self.create_id('campaign')),
            'name': str(raw.get('name') or 'campaign')[:80],
            'startDrawNo': start_draw_no,
            'weeks': weeks,
            'setsPerWeek': sets_per_week,
            'strategyRequest': self.normalize_strategy_request(raw.get('strategyRequest') or create_default_strategy_request('ensemble_weighted')) if raw.get('strategyRequest') else None,
            'createdAt': str(raw.get('createdAt') or dt.datetime.now().isoformat()),
            'memo': str(raw.get('memo') or '')[:200],
        }

    def normalize_record_id(self, value: Any, prefix: str) -> str:
        text = str(value or '').strip()
        if re.fullmatch(r'[A-Za-z0-9_-]{1,120}', text):
            return text
        return self.create_id(prefix)

    def normalize_pension720_ticket(self, raw: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict):
            return None
        try:
            group = int(str(raw.get('group')))
        except (TypeError, ValueError):
            return None
        number = normalize_six_digits(raw.get('number'))
        if group < 1 or group > 5 or not number:
            return None
        target_draw_no = normalize_positive_int(raw.get('targetDrawNo'))
        source = str(raw.get('source') or 'import')
        if source not in {'recommendation', 'campaign', 'import'}:
            source = 'import'
        try:
            score = float(raw.get('score') or 0)
        except (TypeError, ValueError):
            score = 0.0
        return {
            'id': self.normalize_record_id(raw.get('id'), 'p720'),
            'group': group,
            'number': number['number'],
            'digits': number['digits'],
            'source': source,
            'targetDrawNo': target_draw_no,
            'campaignId': str(raw.get('campaignId') or '').strip()[:120],
            'strategyRequest': self.normalize_pension720_strategy_request(raw.get('strategyRequest')) if raw.get('strategyRequest') else None,
            'score': score,
            'memo': str(raw.get('memo') or '')[:200],
            'createdAt': str(raw.get('createdAt') or dt.datetime.now().isoformat()),
            'checked': self.normalize_pension720_checked(raw.get('checked')),
        }

    def normalize_pension720_checked(self, raw: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict):
            return None
        checked_draw = normalize_positive_int(raw.get('drawNo'))
        if checked_draw is None:
            return None
        raw_rank = raw.get('rank')
        rank: Any
        if raw_rank == 'bonus':
            rank = 'bonus'
        elif raw_rank is None:
            rank = 0
        else:
            try:
                rank = max(0, min(7, int(raw_rank)))
            except (TypeError, ValueError):
                rank = 0
        return {
            'drawNo': checked_draw,
            'rank': rank,
            'label': str(raw.get('label') or '')[:40],
            'checkedAt': str(raw.get('checkedAt') or dt.datetime.now().isoformat()),
        }

    def build_pension720_ticket_key(self, ticket: Dict[str, Any]) -> str:
        return '|'.join(
            [
                str(ticket.get('group') or 0),
                str(ticket.get('number') or ''),
                str(ticket.get('targetDrawNo') or '-'),
                str(ticket.get('campaignId') or '-'),
            ]
        )

    def merge_pension720_tickets(self, existing: Sequence[Any], incoming: Sequence[Any]) -> List[Dict[str, Any]]:
        by_key: Dict[str, Dict[str, Any]] = {}
        for item in [*(existing or []), *(incoming or [])]:
            ticket = self.normalize_pension720_ticket(item)
            if not ticket:
                continue
            key = self.build_pension720_ticket_key(ticket)
            if key not in by_key:
                by_key[key] = ticket
        rows = sorted(by_key.values(), key=lambda item: str(item.get('createdAt') or ''), reverse=True)
        return rows[: int(APP_CONFIG['MAX_PENSION720_TICKETS'])]

    def normalize_pension720_campaign(self, raw: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict):
            return None
        start_draw_no = normalize_positive_int(raw.get('startDrawNo'))
        weeks = normalize_positive_int(raw.get('weeks'))
        sets_per_draw = normalize_positive_int(raw.get('setsPerDraw') if raw.get('setsPerDraw') is not None else raw.get('setsPerWeek'))
        if start_draw_no is None or weeks is None or sets_per_draw is None:
            return None
        if weeks > int(APP_CONFIG['MAX_CAMPAIGN_WEEKS']) or sets_per_draw > int(APP_CONFIG['MAX_CAMPAIGN_SETS_PER_WEEK']):
            return None
        if weeks * sets_per_draw > int(APP_CONFIG['MAX_CAMPAIGN_TOTAL_TICKETS']):
            return None
        return {
            'id': self.normalize_record_id(raw.get('id'), 'p720_campaign'),
            'name': str(raw.get('name') or 'pension720 campaign')[:80],
            'startDrawNo': start_draw_no,
            'weeks': weeks,
            'setsPerDraw': sets_per_draw,
            'strategyRequest': self.normalize_pension720_strategy_request(raw.get('strategyRequest')) if raw.get('strategyRequest') else None,
            'createdAt': str(raw.get('createdAt') or dt.datetime.now().isoformat()),
            'memo': str(raw.get('memo') or '')[:200],
        }

    def merge_pension720_campaigns(self, existing: Sequence[Any], incoming: Sequence[Any]) -> List[Dict[str, Any]]:
        by_id: Dict[str, Dict[str, Any]] = {}
        for item in [*(incoming or []), *(existing or [])]:
            campaign = self.normalize_pension720_campaign(item)
            if campaign and campaign['id'] not in by_id:
                by_id[campaign['id']] = campaign
        return sorted(by_id.values(), key=lambda item: str(item.get('createdAt') or ''), reverse=True)

    def build_ticket_key(self, ticket: Dict[str, Any]) -> str:
        strategy_snapshot = self.stable_stringify(ticket.get('strategyRequest')) if ticket.get('strategyRequest') else '-'
        return '|'.join([
            str(ticket.get('targetDrawNo') or 0),
            str(ticket.get('source') or '-'),
            str(ticket.get('campaignId') or '-'),
            ','.join(str(value) for value in ticket.get('numbers', [])),
            strategy_snapshot or '-',
        ])

    def merge_ticket_entries(self, existing: Sequence[Any], incoming: Sequence[Any]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        key_to_index: Dict[str, int] = {}

        def push_ticket(raw_ticket: Any) -> None:
            ticket = self.normalize_ticket_entry(raw_ticket)
            if not ticket:
                return
            key = self.build_ticket_key(ticket)
            if key in key_to_index:
                current = merged[key_to_index[key]]
                current['quantity'] = self.normalize_ticket_quantity(self.get_ticket_quantity(current) + self.get_ticket_quantity(ticket))
                return
            key_to_index[key] = len(merged)
            merged.append(ticket)

        for item in existing or []:
            push_ticket(item)
        for item in incoming or []:
            push_ticket(item)
        return merged

