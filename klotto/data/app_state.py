from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, cast
from uuid import uuid4

from klotto.config import APP_CONFIG
from klotto.core.lotto_rules import calculate_rank, normalize_numbers, normalize_positive_int, safe_int
from klotto.core.strategy_filters import sanitize_filters
from klotto.core.strategy_catalog import create_default_strategy_request
from klotto.data.store_utils import load_json_data, save_json_atomic
from klotto.logging import logger


class AppStateStore:
    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or APP_CONFIG['APP_STATE_FILE']
        self.favorites_file = APP_CONFIG['FAVORITES_FILE']
        self.history_file = APP_CONFIG['HISTORY_FILE']
        self.settings_file = APP_CONFIG['SETTINGS_FILE']
        self.state: Dict[str, Any] = self._load_state()

    def create_default_state(self) -> Dict[str, Any]:
        return {
            'favorites': [],
            'history': [],
            'ticketBook': [],
            'campaigns': [],
            'strategyPrefs': {
                'generator': create_default_strategy_request('ensemble_weighted'),
                'ai': create_default_strategy_request('ensemble_weighted'),
                'backtest': create_default_strategy_request('random_baseline'),
            },
            'strategyPresets': [],
            'alertPrefs': {
                'enableInApp': True,
                'enableSystemNotification': False,
                'notifyOnNewResult': True,
            },
            'syncMeta': {
                'mode': 'automatic_fallback',
                'currentSource': '기본 자동 동기화',
                'lastSuccessAt': '',
                'lastSuccessDrawNo': 0,
                'lastFailureAt': '',
                'lastFailureMessage': '',
                'lastWarningAt': '',
                'lastWarningMessage': '',
            },
            'dataHealth': {
                'availability': 'none',
                'source': 'none',
                'latestDrawNo': 0,
                'message': '',
            },
            'theme': 'light',
            'windowGeometry': None,
            'proxyUrl': '',
            'generatorOptions': {
                'num_sets': 5,
                'fixed_nums': '',
                'exclude_nums': '',
                'check_consecutive': True,
                'consecutive_limit': 2,
            },
        }

    def clone_serializable_value(self, value: Any) -> Any:
        if value is None or not isinstance(value, (dict, list, tuple)):
            return value
        if isinstance(value, (list, tuple)):
            return [self.clone_serializable_value(item) for item in value]
        cloned: Dict[str, Any] = {}
        for key, item in value.items():
            if item is None or isinstance(item, (str, int, float, bool, list, tuple, dict)):
                cloned[key] = self.clone_serializable_value(item)
        return cloned

    def create_id(self, prefix: str = 'id') -> str:
        return f'{prefix}_{uuid4()}'

    def stable_stringify(self, value: Any) -> str:
        try:
            return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        except TypeError:
            return ''

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

    def _load_state(self) -> Dict[str, Any]:
        raw = load_json_data(self.state_file, 'app_state', None)
        if isinstance(raw, dict):
            return self.merge_state(raw)
        migrated = self._migrate_legacy_state()
        save_json_atomic(self.state_file, migrated, 'app_state')
        return migrated

    def _migrate_legacy_state(self) -> Dict[str, Any]:
        defaults = self.create_default_state()
        favorites = load_json_data(self.favorites_file, 'favorites', [])
        history = load_json_data(self.history_file, 'history', [])
        settings = load_json_data(self.settings_file, 'settings', {})
        state = dict(defaults)
        state['favorites'] = [entry for entry in (self.normalize_favorite_entry(item) for item in favorites or []) if entry]
        state['history'] = self.merge_history_entries([], history or [])
        if isinstance(settings, dict):
            theme = settings.get('theme')
            if theme in {'light', 'dark'}:
                state['theme'] = theme
            state['windowGeometry'] = settings.get('window_geometry')
            raw_options = settings.get('options')
            options: Dict[str, Any] = raw_options if isinstance(raw_options, dict) else {}
            state['generatorOptions'] = self.normalize_generator_options({**defaults['generatorOptions'], **options})
        logger.info('Migrated legacy favorites/history/settings into app_state.json')
        return state

    def merge_state(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        defaults = self.create_default_state()
        state = dict(defaults)
        state['favorites'] = [entry for entry in (self.normalize_favorite_entry(item) for item in raw.get('favorites', [])) if entry]
        state['history'] = self.merge_history_entries([], raw.get('history', []))
        state['ticketBook'] = self.merge_ticket_entries([], raw.get('ticketBook', []))
        state['campaigns'] = [entry for entry in (self.normalize_campaign_entry(item) for item in raw.get('campaigns', [])) if entry]
        raw_strategy_prefs = raw.get('strategyPrefs')
        raw_alert_prefs = raw.get('alertPrefs')
        raw_sync_meta = raw.get('syncMeta')
        raw_data_health = raw.get('dataHealth')
        raw_generator_options = raw.get('generatorOptions')
        incoming_prefs: Dict[str, Any] = raw_strategy_prefs if isinstance(raw_strategy_prefs, dict) else {}
        alert_prefs_raw: Dict[str, Any] = raw_alert_prefs if isinstance(raw_alert_prefs, dict) else {}
        sync_meta_raw: Dict[str, Any] = raw_sync_meta if isinstance(raw_sync_meta, dict) else {}
        data_health_raw: Dict[str, Any] = raw_data_health if isinstance(raw_data_health, dict) else {}
        generator_options_raw: Dict[str, Any] = raw_generator_options if isinstance(raw_generator_options, dict) else {}
        state['strategyPrefs'] = {
            'generator': self.normalize_strategy_request(incoming_prefs.get('generator') or defaults['strategyPrefs']['generator']),
            'ai': self.normalize_strategy_request(incoming_prefs.get('ai') or defaults['strategyPrefs']['ai']),
            'backtest': self.normalize_strategy_request(incoming_prefs.get('backtest') or defaults['strategyPrefs']['backtest']),
        }
        state['strategyPresets'] = [preset for preset in (self.normalize_strategy_preset(item) for item in raw.get('strategyPresets', [])) if preset]
        state['alertPrefs'] = {**defaults['alertPrefs'], **alert_prefs_raw}
        state['syncMeta'] = {**defaults['syncMeta'], **sync_meta_raw}
        state['dataHealth'] = {**defaults['dataHealth'], **data_health_raw}
        state['theme'] = raw.get('theme') if raw.get('theme') in {'light', 'dark'} else defaults['theme']
        state['windowGeometry'] = raw.get('windowGeometry')
        state['proxyUrl'] = str(raw.get('proxyUrl') or '')[:500]
        state['generatorOptions'] = self.normalize_generator_options({**defaults['generatorOptions'], **generator_options_raw})
        return state

    def save(self) -> bool:
        return save_json_atomic(self.state_file, self.clone_serializable_value(self.state), 'app_state')

    def normalize_favorite_entry(self, raw: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict):
            return None
        numbers = normalize_numbers(raw.get('numbers'))
        if not numbers:
            return None
        return {
            'numbers': numbers,
            'memo': str(raw.get('memo') or '')[:200],
            'created_at': str(raw.get('created_at') or raw.get('date') or dt.datetime.now().isoformat()),
        }

    def favorite_key(self, numbers: Sequence[int]) -> Tuple[int, ...]:
        return tuple(numbers)

    def normalize_stored_number_entry(self, raw: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict):
            if isinstance(raw, (list, tuple, set)):
                numbers = normalize_numbers(raw)
                if not numbers:
                    return None
                return {'numbers': numbers, 'date': dt.datetime.now().isoformat()}
            return None
        numbers = normalize_numbers(raw.get('numbers'))
        if not numbers:
            return None
        raw_date = raw.get('date') or raw.get('created_at') or dt.datetime.now().isoformat()
        return {'numbers': numbers, 'date': str(raw_date)}

    def merge_history_entries(self, existing: Sequence[Any], incoming: Sequence[Any]) -> List[Dict[str, Any]]:
        merged = [entry for entry in (self.normalize_stored_number_entry(item) for item in [*(existing or []), *(incoming or [])]) if entry]
        merged.sort(key=lambda item: str(item.get('date') or ''), reverse=True)
        max_history = int(APP_CONFIG['MAX_HISTORY'])
        return merged[:max_history]

    def add_favorite(self, numbers: Sequence[int], memo: str = '', *, save: bool = True) -> bool:
        normalized = normalize_numbers(numbers)
        if not normalized:
            return False
        key = self.favorite_key(normalized)
        if any(self.favorite_key(item['numbers']) == key for item in self.state['favorites']):
            return False
        self.state['favorites'].insert(0, {'numbers': normalized, 'memo': str(memo)[:200], 'created_at': dt.datetime.now().isoformat()})
        if save:
            self.save()
        return True

    def add_favorites_many(self, entries: Sequence[Dict[str, Any]]) -> int:
        added = 0
        for entry in entries:
            if self.add_favorite(entry.get('numbers', []), str(entry.get('memo') or ''), save=False):
                added += 1
        if added:
            self.save()
        return added

    def remove_favorite(self, index: int) -> bool:
        if 0 <= index < len(self.state['favorites']):
            self.state['favorites'].pop(index)
            self.save()
            return True
        return False

    def clear_favorites(self) -> None:
        self.state['favorites'] = []
        self.save()

    def add_history_entry(self, numbers: Sequence[int], created_at: Optional[str] = None, *, save: bool = True) -> bool:
        normalized = normalize_numbers(numbers)
        if not normalized:
            return False
        self.state['history'] = self.merge_history_entries(
            [{'numbers': normalized, 'date': created_at or dt.datetime.now().isoformat()}],
            self.state['history'],
        )
        if save:
            self.save()
        return True

    def add_history_many(self, entries: Sequence[Any]) -> List[List[int]]:
        normalized_entries = []
        added_sets: List[List[int]] = []
        for entry in entries:
            normalized = self.normalize_stored_number_entry(entry if isinstance(entry, dict) else {'numbers': entry})
            if not normalized:
                continue
            normalized_entries.append(normalized)
            added_sets.append(list(normalized['numbers']))
        if normalized_entries:
            self.state['history'] = self.merge_history_entries(normalized_entries, self.state['history'])
            self.save()
        return added_sets

    def get_history_number_keys(self) -> set[Tuple[int, ...]]:
        return {tuple(entry['numbers']) for entry in self.state['history'] if isinstance(entry, dict) and normalize_numbers(entry.get('numbers'))}

    def clear_history(self) -> None:
        self.state['history'] = []
        self.save()

    def normalize_ticket_quantity(self, value: Any) -> int:
        return max(1, safe_int(value, 1))

    def get_ticket_quantity(self, ticket: Dict[str, Any]) -> int:
        return self.normalize_ticket_quantity(ticket.get('quantity'))

    def get_total_ticket_count(self, tickets: Optional[Sequence[Dict[str, Any]]] = None) -> int:
        return sum(self.get_ticket_quantity(ticket) for ticket in (tickets or self.state['ticketBook']))

    def normalize_strategy_request(self, raw: Any) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            return create_default_strategy_request('ensemble_weighted')
        strategy_id = str(raw.get('strategyId') or 'ensemble_weighted')
        base = create_default_strategy_request(strategy_id)
        base_params_value = base.get('params')
        base_params: Dict[str, Any] = cast(Dict[str, Any], base_params_value) if isinstance(base_params_value, dict) else {}
        base_filters_value = base.get('filters')
        base_filters: Dict[str, Any] = cast(Dict[str, Any], base_filters_value) if isinstance(base_filters_value, dict) else {}
        raw_params_value = raw.get('params')
        raw_params: Dict[str, Any] = cast(Dict[str, Any], raw_params_value) if isinstance(raw_params_value, dict) else {}
        incoming_params = {**base_params, **raw_params}
        raw_filters_value = raw.get('filters')
        raw_filters: Dict[str, Any] = cast(Dict[str, Any], raw_filters_value) if isinstance(raw_filters_value, dict) else {}
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

    def normalize_strategy_preset(self, raw: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict):
            return None
        scope = str(raw.get('scope') or '').strip()
        name = str(raw.get('name') or '').strip()
        if scope not in {'generator', 'ai', 'backtest'} or not name:
            return None
        return {
            'id': str(raw.get('id') or self.create_id('preset')),
            'scope': scope,
            'name': name[:80],
            'description': str(raw.get('description') or '')[:200],
            'request': self.normalize_strategy_request(raw.get('request') or raw.get('strategyRequest') or {}),
            'createdAt': str(raw.get('createdAt') or dt.datetime.now().isoformat()),
            'updatedAt': str(raw.get('updatedAt') or dt.datetime.now().isoformat()),
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
            checked_rank = safe_int(checked.get('rank'), 0)
            if checked_rank < 0 or checked_rank > 5:
                checked_rank = 0
            if checked_draw is not None:
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

    def get_winning_draw_by_no(self, winning_data: Sequence[Dict[str, Any]], draw_no: int) -> Optional[Dict[str, Any]]:
        target_draw_no = max(1, int(draw_no or 0))
        for draw in winning_data:
            if int(draw.get('draw_no', 0)) == target_draw_no:
                return draw
        return None

    def settle_ticket_entry_if_possible(self, ticket: Dict[str, Any], winning_data: Sequence[Dict[str, Any]]) -> bool:
        if not ticket or ticket.get('checked'):
            return False
        target_draw_no = int(ticket.get('targetDrawNo') or 0)
        if target_draw_no <= 0 or not winning_data:
            return False
        latest_draw_no = max(int(draw.get('draw_no', 0)) for draw in winning_data)
        if target_draw_no > latest_draw_no:
            return False
        draw = self.get_winning_draw_by_no(winning_data, target_draw_no)
        if not draw:
            return False
        winning_numbers = normalize_numbers(draw.get('numbers'))
        bonus = normalize_positive_int(draw.get('bonus'))
        ticket_numbers = normalize_numbers(ticket.get('numbers'))
        if not winning_numbers or ticket_numbers is None or bonus is None:
            return False
        matched = len(set(ticket_numbers) & set(winning_numbers))
        rank = calculate_rank(matched, bonus in ticket_numbers)
        ticket['checked'] = {
            'drawNo': target_draw_no,
            'rank': 0 if rank is None else rank,
            'checkedAt': dt.datetime.now().isoformat(),
        }
        return True

    def settle_tickets_if_possible(self, tickets: Sequence[Dict[str, Any]], winning_data: Sequence[Dict[str, Any]]) -> int:
        settled = 0
        for ticket in tickets:
            if self.settle_ticket_entry_if_possible(ticket, winning_data):
                settled += self.get_ticket_quantity(ticket)
        return settled

    def add_ticket(self, numbers: Sequence[int], *, source: str = 'import', target_draw_no: int = 0, campaign_id: str = '', strategy_request: Optional[Dict[str, Any]] = None, memo: str = '', winning_data: Optional[Sequence[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        normalized = normalize_numbers(numbers)
        target = normalize_positive_int(target_draw_no)
        if not normalized or target is None:
            return None
        ticket = self.normalize_ticket_entry({
            'numbers': normalized,
            'targetDrawNo': target,
            'source': source,
            'campaignId': campaign_id,
            'strategyRequest': strategy_request,
            'memo': memo,
            'quantity': 1,
        })
        if not ticket:
            return None
        key = self.build_ticket_key(ticket)
        for current in self.state['ticketBook']:
            if self.build_ticket_key(current) == key:
                current['quantity'] = self.normalize_ticket_quantity(self.get_ticket_quantity(current) + 1)
                if winning_data:
                    self.settle_tickets_if_possible([current], winning_data)
                self.save()
                return {'ticket': current, 'inserted': False, 'incremented': True, 'quantity': current['quantity']}
        self.state['ticketBook'].insert(0, ticket)
        if winning_data:
            self.settle_tickets_if_possible([ticket], winning_data)
        self.save()
        return {'ticket': ticket, 'inserted': True, 'incremented': False, 'quantity': ticket['quantity']}

    def add_tickets_bulk(self, items: Sequence[Any], *, winning_data: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, int]:
        key_to_ticket = {self.build_ticket_key(ticket): ticket for ticket in self.state['ticketBook']}
        inserted_rows = 0
        incremented_rows = 0
        added_quantity = 0
        touched: List[Dict[str, Any]] = []
        for raw in items:
            ticket = self.normalize_ticket_entry(raw)
            if not ticket:
                continue
            key = self.build_ticket_key(ticket)
            quantity = self.get_ticket_quantity(ticket)
            added_quantity += quantity
            if key in key_to_ticket:
                current = key_to_ticket[key]
                current['quantity'] = self.normalize_ticket_quantity(self.get_ticket_quantity(current) + quantity)
                touched.append(current)
                incremented_rows += 1
            else:
                self.state['ticketBook'].insert(0, ticket)
                key_to_ticket[key] = ticket
                touched.append(ticket)
                inserted_rows += 1
        if touched and winning_data:
            self.settle_tickets_if_possible(touched, winning_data)
        if inserted_rows or incremented_rows:
            self.save()
        return {
            'insertedRows': inserted_rows,
            'incrementedRows': incremented_rows,
            'addedQuantity': added_quantity,
            'affectedRows': inserted_rows + incremented_rows,
        }

    def remove_ticket(self, ticket_id: str) -> bool:
        before = len(self.state['ticketBook'])
        self.state['ticketBook'] = [ticket for ticket in self.state['ticketBook'] if ticket.get('id') != ticket_id]
        removed = before != len(self.state['ticketBook'])
        if removed:
            self.prune_orphan_campaigns(save=False)
            self.save()
        return removed

    def clear_ticket_book(self, filter_name: str = 'all') -> int:
        def is_pending(ticket: Dict[str, Any]) -> bool:
            return not ticket.get('checked')

        def is_win(ticket: Dict[str, Any]) -> bool:
            return bool(ticket.get('checked')) and int(ticket['checked'].get('rank', 0)) > 0

        def is_lose(ticket: Dict[str, Any]) -> bool:
            return bool(ticket.get('checked')) and int(ticket['checked'].get('rank', 0)) == 0

        before = self.get_total_ticket_count()
        if filter_name == 'pending':
            self.state['ticketBook'] = [ticket for ticket in self.state['ticketBook'] if not is_pending(ticket)]
        elif filter_name == 'win':
            self.state['ticketBook'] = [ticket for ticket in self.state['ticketBook'] if not is_win(ticket)]
        elif filter_name == 'lose':
            self.state['ticketBook'] = [ticket for ticket in self.state['ticketBook'] if not is_lose(ticket)]
        else:
            self.state['ticketBook'] = []
        removed = before - self.get_total_ticket_count()
        self.prune_orphan_campaigns(save=False)
        self.save()
        return removed

    def prune_orphan_campaigns(self, *, save: bool = True) -> Dict[str, Any]:
        linked_ids = {str(ticket.get('campaignId') or '').strip() for ticket in self.state['ticketBook'] if ticket.get('campaignId')}
        kept = []
        removed = []
        for campaign in self.state['campaigns']:
            campaign_id = str(campaign.get('id') or '').strip()
            if campaign_id and campaign_id in linked_ids:
                kept.append(campaign)
            else:
                removed.append(campaign)
        if removed:
            self.state['campaigns'] = kept
            if save:
                self.save()
        return {'campaigns': self.state['campaigns'], 'removed': removed}

    def add_campaign(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        normalized = self.normalize_campaign_entry(entry)
        if not normalized:
            return None
        self.state['campaigns'].insert(0, normalized)
        self.save()
        return normalized

    def remove_campaign(self, campaign_id: str, *, cascade_tickets: bool = True) -> Dict[str, Any]:
        before_campaigns = len(self.state['campaigns'])
        self.state['campaigns'] = [campaign for campaign in self.state['campaigns'] if campaign.get('id') != campaign_id]
        removed_campaign = before_campaigns != len(self.state['campaigns'])
        removed_tickets = 0
        if cascade_tickets:
            before_tickets = self.get_total_ticket_count()
            self.state['ticketBook'] = [ticket for ticket in self.state['ticketBook'] if ticket.get('campaignId') != campaign_id]
            removed_tickets = before_tickets - self.get_total_ticket_count()
        if removed_campaign or removed_tickets:
            self.save()
        return {'removedCampaign': removed_campaign, 'removedTickets': removed_tickets}

    def clear_campaigns(self, *, cascade_tickets: bool = True) -> Dict[str, int]:
        campaign_ids = [campaign.get('id') for campaign in self.state['campaigns'] if campaign.get('id')]
        removed_campaigns = len(campaign_ids)
        removed_tickets = 0
        self.state['campaigns'] = []
        if cascade_tickets and campaign_ids:
            before_tickets = self.get_total_ticket_count()
            id_set = set(campaign_ids)
            self.state['ticketBook'] = [ticket for ticket in self.state['ticketBook'] if ticket.get('campaignId') not in id_set]
            removed_tickets = before_tickets - self.get_total_ticket_count()
        self.save()
        return {'removedCampaigns': removed_campaigns, 'removedTickets': removed_tickets}

    def set_strategy_pref(self, scope: str, request: Dict[str, Any]) -> None:
        if scope not in {'generator', 'ai', 'backtest'}:
            return
        self.state['strategyPrefs'][scope] = self.normalize_strategy_request(request)
        self.save()

    def get_strategy_pref(self, scope: str) -> Dict[str, Any]:
        return self.normalize_strategy_request(self.state['strategyPrefs'].get(scope))

    def save_strategy_preset(self, scope: str, name: str, request: Dict[str, Any], description: str = '') -> Optional[Dict[str, Any]]:
        preset = self.normalize_strategy_preset({'scope': scope, 'name': name, 'request': request, 'description': description})
        if not preset:
            return None
        self.state['strategyPresets'] = [item for item in self.state['strategyPresets'] if not (item.get('scope') == scope and item.get('name') == name)]
        self.state['strategyPresets'].insert(0, preset)
        self.state['strategyPresets'] = self.state['strategyPresets'][: int(APP_CONFIG['MAX_STRATEGY_PRESETS'])]
        self.save()
        return preset

    def delete_strategy_preset(self, preset_id: str) -> bool:
        before = len(self.state['strategyPresets'])
        self.state['strategyPresets'] = [preset for preset in self.state['strategyPresets'] if preset.get('id') != preset_id]
        removed = before != len(self.state['strategyPresets'])
        if removed:
            self.save()
        return removed

    def set_sync_meta(self, **updates: Any) -> None:
        self.state['syncMeta'] = {**self.state['syncMeta'], **updates}
        self.save()

    def set_data_health(self, **updates: Any) -> None:
        self.state['dataHealth'] = {**self.state['dataHealth'], **updates}
        self.save()

    def export_backup_payload(self) -> Dict[str, Any]:
        return {
            'app': APP_CONFIG['APP_NAME'],
            'version': APP_CONFIG['VERSION'],
            'exportedAt': dt.datetime.now().isoformat(),
            'state': self.clone_serializable_value(self.state),
        }

    def import_backup_payload(self, payload: Dict[str, Any], *, mode: str = 'merge', winning_data: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, int]:
        incoming_state = payload.get('state') if isinstance(payload.get('state'), dict) else payload
        if not isinstance(incoming_state, dict):
            raise ValueError('백업 형식이 올바르지 않습니다.')
        normalized = self.merge_state(incoming_state)
        if mode == 'overwrite':
            self.state = normalized
        else:
            self.state['favorites'] = [*self.state['favorites']]
            self.add_favorites_many(normalized['favorites'])
            self.state['history'] = self.merge_history_entries(normalized['history'], self.state['history'])
            self.state['ticketBook'] = self.merge_ticket_entries(self.state['ticketBook'], normalized['ticketBook'])
            existing_campaign_ids = {item.get('id') for item in self.state['campaigns']}
            for campaign in normalized['campaigns']:
                if campaign.get('id') not in existing_campaign_ids:
                    self.state['campaigns'].append(campaign)
            self.state['strategyPrefs'] = normalized['strategyPrefs']
            self.state['strategyPresets'] = normalized['strategyPresets']
            self.state['alertPrefs'] = normalized['alertPrefs']
            self.state['theme'] = normalized['theme']
            self.state['proxyUrl'] = normalized['proxyUrl']
            self.state['generatorOptions'] = normalized['generatorOptions']
            self.state['syncMeta'] = normalized['syncMeta']
            self.state['dataHealth'] = normalized['dataHealth']
        if winning_data:
            self.settle_tickets_if_possible(self.state['ticketBook'], winning_data)
        self.prune_orphan_campaigns(save=False)
        self.save()
        return {
            'favorites': len(self.state['favorites']),
            'history': len(self.state['history']),
            'tickets': self.get_total_ticket_count(),
            'campaigns': len(self.state['campaigns']),
        }


_shared_store: Optional[AppStateStore] = None



def get_shared_store() -> AppStateStore:
    global _shared_store
    if _shared_store is None:
        _shared_store = AppStateStore()
    return _shared_store


__all__ = ['AppStateStore', 'get_shared_store']
