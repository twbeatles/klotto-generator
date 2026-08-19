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


class FavoritesStoreMixin(StoreAPI):
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

