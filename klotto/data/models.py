from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional

StrategyScope = Literal['generator', 'ai', 'backtest']
DataHealthAvailability = Literal['full', 'partial', 'none']
TicketSource = Literal['generator', 'ai', 'import']
PayoutMode = Literal['hybrid_dynamic_first', 'fast_fixed']


@dataclass(slots=True)
class StrategyParams:
    simulationCount: int = 5000
    lookbackWindow: int = 20
    wheelPoolSize: Optional[int] = None
    wheelGuarantee: Optional[int] = None
    seed: Optional[int] = None
    payoutMode: PayoutMode = 'hybrid_dynamic_first'


@dataclass(slots=True)
class StrategyFilters:
    oddEven: Optional[List[int]] = None
    highLow: Optional[List[int]] = None
    sumRange: Optional[List[int]] = None
    acRange: Optional[List[int]] = None
    maxConsecutivePairs: Optional[int] = None
    endDigitUniqueMin: Optional[int] = None


@dataclass(slots=True)
class StrategyRequest:
    strategy_id: str
    evidence_tier: str = 'A'
    params: StrategyParams = field(default_factory=StrategyParams)
    filters: StrategyFilters = field(default_factory=StrategyFilters)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'strategyId': self.strategy_id,
            'evidenceTier': self.evidence_tier,
            'params': asdict(self.params),
            'filters': asdict(self.filters),
        }


@dataclass(slots=True)
class TicketCheck:
    draw_no: int
    rank: int
    checked_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            'drawNo': self.draw_no,
            'rank': self.rank,
            'checkedAt': self.checked_at,
        }


@dataclass(slots=True)
class TicketEntry:
    id: str
    numbers: List[int]
    target_draw_no: int
    source: TicketSource = 'import'
    campaign_id: str = ''
    strategy_request: Optional[Dict[str, Any]] = None
    memo: str = ''
    created_at: str = ''
    checked: Optional[TicketCheck] = None
    quantity: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'numbers': list(self.numbers),
            'targetDrawNo': self.target_draw_no,
            'source': self.source,
            'campaignId': self.campaign_id,
            'strategyRequest': self.strategy_request,
            'memo': self.memo,
            'createdAt': self.created_at,
            'checked': self.checked.to_dict() if self.checked else None,
            'quantity': self.quantity,
        }


@dataclass(slots=True)
class CampaignEntry:
    id: str
    name: str
    start_draw_no: int
    weeks: int
    sets_per_week: int
    strategy_request: Optional[Dict[str, Any]] = None
    created_at: str = ''
    memo: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'startDrawNo': self.start_draw_no,
            'weeks': self.weeks,
            'setsPerWeek': self.sets_per_week,
            'strategyRequest': self.strategy_request,
            'createdAt': self.created_at,
            'memo': self.memo,
        }


@dataclass(slots=True)
class BacktestComparison:
    strategy_id: str
    payout_mode: str
    draws: int
    tickets: int
    requested_tickets: int
    generated_tickets: int
    cost: int
    total_prize: int
    counts: Dict[int, int] = field(default_factory=dict)
    win_count: int = 0
    roi: float = 0.0
    hit_rate: float = 0.0
    fill_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'strategyId': self.strategy_id,
            'payoutMode': self.payout_mode,
            'draws': self.draws,
            'tickets': self.tickets,
            'requestedTickets': self.requested_tickets,
            'generatedTickets': self.generated_tickets,
            'cost': self.cost,
            'totalPrize': self.total_prize,
            'counts': dict(self.counts),
            'winCount': self.win_count,
            'roi': self.roi,
            'hitRate': self.hit_rate,
            'fillRate': self.fill_rate,
        }


@dataclass(slots=True)
class SyncMeta:
    mode: str = 'automatic_fallback'
    current_source: str = '기본 자동 동기화'
    last_success_at: str = ''
    last_success_draw_no: int = 0
    last_failure_at: str = ''
    last_failure_message: str = ''
    last_warning_at: str = ''
    last_warning_message: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return {
            'mode': self.mode,
            'currentSource': self.current_source,
            'lastSuccessAt': self.last_success_at,
            'lastSuccessDrawNo': self.last_success_draw_no,
            'lastFailureAt': self.last_failure_at,
            'lastFailureMessage': self.last_failure_message,
            'lastWarningAt': self.last_warning_at,
            'lastWarningMessage': self.last_warning_message,
        }


@dataclass(slots=True)
class DataHealth:
    availability: DataHealthAvailability = 'none'
    source: str = 'none'
    latest_draw_no: int = 0
    message: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return {
            'availability': self.availability,
            'source': self.source,
            'latestDrawNo': self.latest_draw_no,
            'message': self.message,
        }


@dataclass(slots=True)
class AlertPrefs:
    enable_in_app: bool = True
    enable_system_notification: bool = False
    notify_on_new_result: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            'enableInApp': self.enable_in_app,
            'enableSystemNotification': self.enable_system_notification,
            'notifyOnNewResult': self.notify_on_new_result,
        }


@dataclass(slots=True)
class AppState:
    favorites: List[Dict[str, Any]] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    ticket_book: List[Dict[str, Any]] = field(default_factory=list)
    campaigns: List[Dict[str, Any]] = field(default_factory=list)
    strategy_prefs: Dict[str, Any] = field(default_factory=dict)
    strategy_presets: List[Dict[str, Any]] = field(default_factory=list)
    alert_prefs: Dict[str, Any] = field(default_factory=dict)
    sync_meta: Dict[str, Any] = field(default_factory=dict)
    data_health: Dict[str, Any] = field(default_factory=dict)
    theme: str = 'light'
    window_geometry: Optional[str] = None
    proxy_url: str = ''
    generator_options: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'favorites': list(self.favorites),
            'history': list(self.history),
            'ticketBook': list(self.ticket_book),
            'campaigns': list(self.campaigns),
            'strategyPrefs': dict(self.strategy_prefs),
            'strategyPresets': list(self.strategy_presets),
            'alertPrefs': dict(self.alert_prefs),
            'syncMeta': dict(self.sync_meta),
            'dataHealth': dict(self.data_health),
            'theme': self.theme,
            'windowGeometry': self.window_geometry,
            'proxyUrl': self.proxy_url,
            'generatorOptions': dict(self.generator_options),
        }


__all__ = [
    'AlertPrefs',
    'AppState',
    'BacktestComparison',
    'CampaignEntry',
    'DataHealth',
    'StrategyFilters',
    'StrategyParams',
    'StrategyRequest',
    'SyncMeta',
    'TicketCheck',
    'TicketEntry',
]
