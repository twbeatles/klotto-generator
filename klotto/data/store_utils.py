import json
import os
from pathlib import Path
from typing import Any, Optional

from klotto.logging import logger


def load_json_data(path: Optional[Path], label: str, default: Any) -> Any:
    if path is None or not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, list):
            logger.info("Loaded %s %s entries", len(data), label)
        return data
    except Exception as exc:
        logger.error("Failed to load %s: %s", label, exc)
        return default


def save_json_atomic(path: Optional[Path], payload: Any, label: str) -> bool:
    if path is None:
        return False

    temp_file: Optional[Path] = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_file = path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

        if path.exists():
            os.replace(temp_file, path)
        else:
            os.rename(temp_file, path)
        return True
    except Exception as exc:
        logger.error("Failed to save %s: %s", label, exc)
        try:
            if temp_file and temp_file.exists():
                temp_file.unlink()
        except Exception:
            pass
        return False


__all__ = ["load_json_data", "save_json_atomic"]
