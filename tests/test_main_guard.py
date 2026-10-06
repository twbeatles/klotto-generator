from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from klotto.main import acquire_app_lock, release_app_lock


def test_second_lock_acquisition_is_refused(tmp_path: Path):
    try:
        assert acquire_app_lock(tmp_path / 'one') is True
        assert acquire_app_lock(tmp_path / 'one') is False
    finally:
        release_app_lock()


def test_lock_can_be_reacquired_after_release(tmp_path: Path):
    try:
        assert acquire_app_lock(tmp_path / 'two') is True
    finally:
        release_app_lock()
    try:
        assert acquire_app_lock(tmp_path / 'two') is True
    finally:
        release_app_lock()
