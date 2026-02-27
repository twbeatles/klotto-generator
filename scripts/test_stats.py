try:
    from scripts.common import ensure_repo_on_path
except ModuleNotFoundError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.common import ensure_repo_on_path

ensure_repo_on_path()

from klotto.core.stats import WinningStatsManager

m = WinningStatsManager()
print(f'Loaded {len(m.winning_data)} records')
a = m.get_frequency_analysis()
print(f'Total draws: {a.get("total_draws", 0)}')
if a.get("hot_numbers"):
    print(f'Hot numbers (top 5): {a["hot_numbers"][:5]}')
