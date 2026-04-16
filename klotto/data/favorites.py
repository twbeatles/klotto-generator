from __future__ import annotations

from typing import Any, Dict, List, Optional

from klotto.data.app_state import AppStateStore, get_shared_store


class FavoritesManager:
    """Backward-compatible wrapper over the unified app-state store."""

    def __init__(self, store: Optional[AppStateStore] = None):
        self.store = store or get_shared_store()

    def add(self, numbers: List[int], memo: str = '', save: bool = True) -> bool:
        added = self.store.add_favorite(numbers, memo, save=False)
        if added and save:
            self.store.save()
        return added

    def add_many(self, items: List[Dict[str, Any]]) -> int:
        return self.store.add_favorites_many(items)

    def remove(self, index: int) -> None:
        self.store.remove_favorite(index)

    def clear(self) -> None:
        self.store.clear_favorites()

    def get_all(self) -> List[Dict[str, Any]]:
        return list(self.store.state['favorites'])
