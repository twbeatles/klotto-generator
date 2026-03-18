"""
Legacy compatibility wrapper for Lotto Generator Pro.

This module preserves the historical single-file import surface while delegating
all implementation to the package modules under ``klotto``.
"""

from klotto.config import APP_CONFIG, DHLOTTERY_API_URL, LOTTO_COLORS, THEMES
from klotto.core.analysis import NumberAnalyzer
from klotto.core.generator import SmartNumberGenerator
from klotto.core.stats import WinningStatsManager
from klotto.data.exporter import DataExporter
from klotto.data.favorites import FavoritesManager
from klotto.data.history import HistoryManager
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
    "DHLOTTERY_API_URL",
    "DataExporter",
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
    "QRCodeDialog",
    "RealStatsDialog",
    "ResultRow",
    "SmartNumberGenerator",
    "StatisticsDialog",
    "THEMES",
    "ThemeManager",
    "WinningCheckDialog",
    "WinningInfoWidget",
    "WinningStatsManager",
    "exception_hook",
    "logger",
    "main",
    "setup_logging",
]


if __name__ == "__main__":
    main()
