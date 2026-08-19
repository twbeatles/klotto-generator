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



class StrategyPrefsMixin(StoreAPI):
    def set_strategy_pref(self, scope: str, request: Dict[str, Any]) -> None:
        if scope not in {'generator', 'ai', 'backtest', 'pension720'}:
            return
        self.state['strategyPrefs'][scope] = self.normalize_pension720_strategy_request(request) if scope == 'pension720' else self.normalize_strategy_request(request)
        self.save()

    def get_strategy_pref(self, scope: str) -> Dict[str, Any]:
        if scope == 'pension720':
            return self.normalize_pension720_strategy_request(self.state['strategyPrefs'].get(scope))
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

    def set_pension720_data_health(self, **updates: Any) -> None:
        self.state['pension720DataHealth'] = self.normalize_pension720_data_health({**self.state['pension720DataHealth'], **updates})
        self.save()

