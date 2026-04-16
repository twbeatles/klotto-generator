from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from klotto.data.app_state import AppStateStore, get_shared_store


class HistoryManager:
    """Backward-compatible wrapper over the unified app-state store."""

    def __init__(self, store: Optional[AppStateStore] = None):
        self.store = store or get_shared_store()

    def add(self, numbers: List[int], save: bool = True) -> bool:
        added = self.store.add_history_entry(numbers, save=False)
        if added and save:
            self.store.save()
        return added

    def add_many(self, numbers_sets: List[Any]) -> List[List[int]]:
        return self.store.add_history_many(numbers_sets)

    def is_duplicate(self, numbers: List[int]) -> bool:
        return tuple(numbers) in self.get_number_keys()

    def get_number_keys(self) -> Set[Tuple[int, ...]]:
        return self.store.get_history_number_keys()

    def get_all(self) -> List[Dict[str, Any]]:
        return [
            {
                'numbers': list(entry.get('numbers', [])),
                'date': entry.get('date', ''),
                'created_at': entry.get('date', ''),
            }
            for entry in self.store.state['history']
        ]

    def get_recent(self, count: int = 50) -> List[Dict[str, Any]]:
        return self.get_all()[:count]

    def clear(self) -> None:
        self.store.clear_history()

    def get_statistics(self) -> Dict[str, Any]:
        history = self.get_all()
        if not history:
            return {}
        number_counts = {i: 0 for i in range(1, 46)}
        for entry in history:
            for number in entry.get('numbers', []):
                number_counts[int(number)] += 1
        sorted_by_count = sorted(number_counts.items(), key=lambda item: item[1], reverse=True)
        return {
            'total_sets': len(history),
            'number_counts': number_counts,
            'most_common': sorted_by_count[:10],
            'least_common': sorted_by_count[-10:],
        }
