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



class HistoryStoreMixin(StoreAPI):
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

