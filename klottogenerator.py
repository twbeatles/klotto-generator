"""
Legacy compatibility wrapper for 로또·연금복권 프로.

This module preserves the historical single-file import surface while delegating
all implementation to the package modules under ``klotto``.
"""

from klotto.config import APP_CONFIG, DHLOTTERY_API_URL, LOTTO_COLORS, THEMES
from klotto.core.analysis import NumberAnalyzer
from klotto.core.backtest import BacktestResult, run_backtest
from klotto.core.generator import SmartNumberGenerator
from klotto.core.pension720_engine import Pension720Engine
from klotto.core.pension720_strategy_catalog import (
    create_default_pension720_strategy_request,
    list_pension720_strategies,
    resolve_pension720_strategy_id,
)
from klotto.core.stats import WinningStatsManager
from klotto.core.strategy_catalog import (
    create_default_strategy_request,
    list_strategies,
    resolve_strategy_id,
)
from klotto.core.strategy_engine import StrategyEngine
from klotto.data.exporter import DataExporter
from klotto.data.favorites import FavoritesManager
from klotto.data.history import HistoryManager
from klotto.data.models import (
    AlertPrefs,
    AppState,
    BacktestComparison,
    CampaignEntry,
    DataHealth,
    Pension720CampaignEntry,
    Pension720TicketEntry,
    StrategyRequest,
    SyncMeta,
    TicketCheck,
    TicketEntry,
)
from klotto.logging import logger, setup_logging
from klotto.main import exception_hook, main
from klotto.net.client import LottoNetworkManager
from klotto.ui.dialogs import (
    ExportImportDialog,
    FavoritesDialog,
    HistoryDialog,
    QRCodeDialog,
    RealStatsDialog,
    StatisticsDialog,
    WinningCheckDialog,
)
from klotto.ui.main_window import LottoApp
from klotto.ui.theme import ThemeManager
from klotto.ui.widgets import LottoBall, ResultRow, WinningInfoWidget

__all__ = [
    "APP_CONFIG",
    "AlertPrefs",
    "AppState",
    "BacktestComparison",
    "BacktestResult",
    "CampaignEntry",
    "DHLOTTERY_API_URL",
    "DataExporter",
    "DataHealth",
    "ExportImportDialog",
    "FavoritesDialog",
    "FavoritesManager",
    "HistoryDialog",
    "HistoryManager",
    "LOTTO_COLORS",
    "LottoApp",
    "LottoBall",
    "LottoNetworkManager",
    "NumberAnalyzer",
    "Pension720CampaignEntry",
    "Pension720Engine",
    "Pension720TicketEntry",
    "QRCodeDialog",
    "RealStatsDialog",
    "ResultRow",
    "SmartNumberGenerator",
    "StrategyEngine",
    "StrategyRequest",
    "StatisticsDialog",
    "SyncMeta",
    "THEMES",
    "TicketCheck",
    "TicketEntry",
    "ThemeManager",
    "WinningCheckDialog",
    "WinningInfoWidget",
    "WinningStatsManager",
    "create_default_strategy_request",
    "create_default_pension720_strategy_request",
    "exception_hook",
    "list_strategies",
    "list_pension720_strategies",
    "logger",
    "main",
    "resolve_strategy_id",
    "resolve_pension720_strategy_id",
    "run_backtest",
    "setup_logging",
]


if __name__ == "__main__":
    main()
