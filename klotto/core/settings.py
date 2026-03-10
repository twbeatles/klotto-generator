import json
from pathlib import Path
from typing import Dict, Any, Optional
from ..config import APP_CONFIG
from ..utils import logger

class SettingsManager:
    """사용자 설정 관리자 (윈도우 크기, 테마, 옵션 등)"""
    
    def __init__(self):
        settings_file = APP_CONFIG.get('SETTINGS_FILE')
        self.settings_file: Optional[Path] = settings_file if isinstance(settings_file, Path) else None
        self.settings: Dict[str, Any] = {
            'theme': 'light',
            'window_geometry': None,
            'options': {
                'num_sets': 5,
                'fixed_nums': '',
                'exclude_nums': '',
                'check_consecutive': False,
                'consecutive_limit': 3,
                'compare_mode': False,
                'smart_gen': True
            }
        }
        if self.settings_file:
            self._load()
    
    def _load(self):
        settings_file = self.settings_file
        if settings_file is None:
            return

        try:
            if settings_file.exists():
                with open(settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 병합 (누락된 키 보존)
                    self.settings.update(data)
                    # options 내부도 병합
                    if 'options' in data:
                         self.settings['options'].update(data['options'])
                logger.info("Settings loaded")
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")

    def save(self):
        settings_file = self.settings_file
        if settings_file is None:
            return

        try:
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
            logger.info("Settings saved")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

    def get(self, key: str, default=None):
        return self.settings.get(key, default)

    def set(self, key: str, value: Any):
        self.settings[key] = value
    
    def get_option(self, key: str, default=None):
        return self.settings['options'].get(key, default)

    def set_option(self, key: str, value: Any):
        self.settings['options'][key] = value
