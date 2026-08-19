from __future__ import annotations

from typing import Optional

from klotto.data.store.backup import BackupStoreMixin
from klotto.data.store.base import StoreBaseMixin
from klotto.data.store.campaigns import CampaignStoreMixin
from klotto.data.store.favorites import FavoritesStoreMixin
from klotto.data.store.history import HistoryStoreMixin
from klotto.data.store.normalization import NormalizationMixin
from klotto.data.store.pension720 import Pension720StoreMixin
from klotto.data.store.strategy_prefs import StrategyPrefsMixin
from klotto.data.store.tickets import TicketStoreMixin


class AppStateStore(
    StoreBaseMixin,
    FavoritesStoreMixin,
    HistoryStoreMixin,
    NormalizationMixin,
    TicketStoreMixin,
    CampaignStoreMixin,
    Pension720StoreMixin,
    StrategyPrefsMixin,
    BackupStoreMixin,
):
    """Unified application state store composed from single-responsibility mixins."""

    pass


_shared_store: Optional[AppStateStore] = None


def get_shared_store() -> AppStateStore:
    global _shared_store
    if _shared_store is None:
        _shared_store = AppStateStore()
    return _shared_store


__all__ = ['AppStateStore', 'get_shared_store']