from __future__ import annotations

import datetime as dt
import json
import re
import shutil
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


class StoreBaseMixin(StoreAPI):
    state_load_issue: Optional[str] = None

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or APP_CONFIG['APP_STATE_FILE']
        self.favorites_file = APP_CONFIG['FAVORITES_FILE']
        self.history_file = APP_CONFIG['HISTORY_FILE']
        self.settings_file = APP_CONFIG['SETTINGS_FILE']
        self.state_load_issue = None
        self.last_save_error: Optional[str] = None
        self.state: Dict[str, Any] = self._load_state()

    def create_default_state(self) -> Dict[str, Any]:
        return {
            'favorites': [],
            'history': [],
            'ticketBook': [],
            'campaigns': [],
            'pension720Tickets': [],
            'pension720Campaigns': [],
            'strategyPrefs': {
                'generator': create_default_strategy_request('ensemble_weighted'),
                'ai': create_default_strategy_request('ensemble_weighted'),
                'backtest': create_default_strategy_request('random_baseline'),
                'pension720': create_default_pension720_strategy_request('mixed_balance'),
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
            'pension720DataHealth': {
                'availability': 'none',
                'source': 'none',
                'latestDrawNo': 0,
                'message': '',
                'updatedAt': '',
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

    def _load_state(self) -> Dict[str, Any]:
        raw = load_json_data(self.state_file, 'app_state', None)
        if isinstance(raw, dict):
            self.state_load_issue = None
            return self.merge_state(raw)
        if raw is not None or self._is_state_file_corrupt():
            # Valid JSON of the wrong type (e.g. a list) is also unusable:
            # preserve the original bytes before replacing it.
            self.state_load_issue = self._preserve_corrupt_state()
        else:
            self.state_load_issue = None
        migrated = self._migrate_legacy_state()
        save_json_atomic(self.state_file, migrated, 'app_state')
        return migrated

    def _is_state_file_corrupt(self) -> bool:
        path = self.state_file
        if path is None or not path.exists():
            return False
        try:
            with open(path, 'r', encoding='utf-8') as file:
                json.load(file)
            return False
        except Exception:
            return True

    def _preserve_corrupt_state(self) -> str:
        timestamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup = self.state_file.with_name(f'{self.state_file.stem}.corrupt-{timestamp}.json')
        try:
            shutil.copy2(self.state_file, backup)
            message = f'손상된 상태 파일을 보존했습니다: {backup}'
        except Exception as exc:
            message = f'손상된 상태 파일을 감지했으나 보존에 실패했습니다: {exc}'
        logger.warning('Corrupt app_state detected; %s', message)
        return message

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
            state['generatorOptions'] = {**defaults['generatorOptions'], **options}
        logger.info('Migrated legacy favorites/history/settings into app_state.json')
        return state

    def merge_state(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        defaults = self.create_default_state()
        state = dict(defaults)
        state['favorites'] = [entry for entry in (self.normalize_favorite_entry(item) for item in raw.get('favorites', [])) if entry]
        state['history'] = self.merge_history_entries([], raw.get('history', []))
        state['ticketBook'] = self.merge_ticket_entries([], raw.get('ticketBook', []))
        state['campaigns'] = [entry for entry in (self.normalize_campaign_entry(item) for item in raw.get('campaigns', [])) if entry]
        state['pension720Tickets'] = self.merge_pension720_tickets([], raw.get('pension720Tickets', []))
        state['pension720Campaigns'] = self.merge_pension720_campaigns([], raw.get('pension720Campaigns', []))
        raw_strategy_prefs = raw.get('strategyPrefs')
        raw_alert_prefs = raw.get('alertPrefs')
        raw_sync_meta = raw.get('syncMeta')
        raw_data_health = raw.get('dataHealth')
        raw_pension720_health = raw.get('pension720DataHealth')
        raw_generator_options = raw.get('generatorOptions')
        incoming_prefs: Dict[str, Any] = raw_strategy_prefs if isinstance(raw_strategy_prefs, dict) else {}
        alert_prefs_raw: Dict[str, Any] = raw_alert_prefs if isinstance(raw_alert_prefs, dict) else {}
        sync_meta_raw: Dict[str, Any] = raw_sync_meta if isinstance(raw_sync_meta, dict) else {}
        data_health_raw: Dict[str, Any] = raw_data_health if isinstance(raw_data_health, dict) else {}
        pension720_health_raw: Dict[str, Any] = raw_pension720_health if isinstance(raw_pension720_health, dict) else {}
        generator_options_raw: Dict[str, Any] = raw_generator_options if isinstance(raw_generator_options, dict) else {}
        state['strategyPrefs'] = {
            'generator': self.normalize_strategy_request(incoming_prefs.get('generator') or defaults['strategyPrefs']['generator']),
            'ai': self.normalize_strategy_request(incoming_prefs.get('ai') or defaults['strategyPrefs']['ai']),
            'backtest': self.normalize_strategy_request(incoming_prefs.get('backtest') or defaults['strategyPrefs']['backtest']),
            'pension720': self.normalize_pension720_strategy_request(incoming_prefs.get('pension720') or defaults['strategyPrefs']['pension720']),
        }
        state['strategyPresets'] = [preset for preset in (self.normalize_strategy_preset(item) for item in raw.get('strategyPresets', [])) if preset]
        state['alertPrefs'] = self.normalize_alert_prefs({**defaults['alertPrefs'], **alert_prefs_raw})
        state['syncMeta'] = {**defaults['syncMeta'], **sync_meta_raw}
        state['dataHealth'] = {**defaults['dataHealth'], **data_health_raw}
        state['pension720DataHealth'] = self.normalize_pension720_data_health({**defaults['pension720DataHealth'], **pension720_health_raw})
        state['theme'] = raw.get('theme') if raw.get('theme') in {'light', 'dark'} else defaults['theme']
        state['windowGeometry'] = raw.get('windowGeometry')
        state['proxyUrl'] = normalize_proxy_url(raw.get('proxyUrl'))[:500]
        state['generatorOptions'] = self.normalize_generator_options({**defaults['generatorOptions'], **generator_options_raw})
        return state

    def save(self) -> bool:
        ok = save_json_atomic(self.state_file, self.clone_serializable_value(self.state), 'app_state')
        if ok:
            self.last_save_error = None
        else:
            self.last_save_error = (
                '상태 저장 실패: '
                + dt.datetime.now().isoformat(timespec='seconds')
            )
            logger.error('Store save failed; last_save_error set')
        return ok

