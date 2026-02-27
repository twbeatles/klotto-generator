from pathlib import Path
import sys


def get_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def ensure_repo_on_path() -> Path:
    root = get_repo_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


def get_default_data_dir() -> Path:
    return get_repo_root() / "data"


def resolve_db_path() -> Path:
    ensure_repo_on_path()
    try:
        from klotto.config import APP_CONFIG
        db_path = APP_CONFIG.get("LOTTO_HISTORY_DB")
        if db_path:
            return Path(db_path)
    except Exception:
        pass
    return get_default_data_dir() / "lotto_history.db"
