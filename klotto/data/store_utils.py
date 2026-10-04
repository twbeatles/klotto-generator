import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from klotto.logging import logger

LOCK_TIMEOUT_S = 10.0
LOCK_STALE_S = 30.0


def _lock_path_for(path: Path) -> Path:
    return path.with_name(f'{path.stem}.lock')


def _try_acquire_lock(lock_path: Path) -> bool:
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    except OSError as exc:
        logger.error('Failed to create lock file %s: %s', lock_path, exc)
        return False
    try:
        os.write(fd, str(os.getpid()).encode('utf-8'))
    except OSError:
        pass
    finally:
        os.close(fd)
    return True


def _is_lock_stale(lock_path: Path) -> bool:
    try:
        age = time.time() - lock_path.stat().st_mtime
    except OSError:
        return True
    return age > LOCK_STALE_S


def acquire_file_lock(path: Path, *, timeout_s: float = LOCK_TIMEOUT_S) -> bool:
    """프로세스 간 저장을 직렬화하는 잠금을 획득한다. 타임아웃 시 False."""
    lock_path = _lock_path_for(path)
    deadline = time.time() + max(0.0, timeout_s)
    while True:
        if _try_acquire_lock(lock_path):
            return True
        if _is_lock_stale(lock_path):
            try:
                lock_path.unlink()
            except OSError:
                pass
            continue
        if time.time() >= deadline:
            logger.error('Timed out waiting for lock file %s', lock_path)
            return False
        time.sleep(0.05)


def release_file_lock(path: Path) -> None:
    try:
        _lock_path_for(path).unlink()
    except OSError:
        pass


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
    locked = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        locked = acquire_file_lock(path)
        if not locked:
            logger.error("Failed to save %s: could not acquire file lock", label)
            return False
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
    finally:
        if locked:
            release_file_lock(path)


__all__ = ["load_json_data", "save_json_atomic", "acquire_file_lock", "release_file_lock"]
