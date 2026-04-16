from __future__ import annotations

from typing import Any, Dict, Optional

from klotto.data.app_state import AppStateStore, get_shared_store


class SettingsManager:
    """Compatibility layer that persists settings inside the unified app state."""

    def __init__(self, store: Optional[AppStateStore] = None):
        self.store = store or get_shared_store()

    @property
    def settings(self) -> Dict[str, Any]:
        return {
            'theme': self.store.state.get('theme', 'light'),
            'window_geometry': self.store.state.get('windowGeometry'),
            'options': dict(self.store.state.get('generatorOptions') or {}),
        }

    def save(self):
        self.store.save()

    def get(self, key: str, default=None):
        return self.settings.get(key, default)

    def set(self, key: str, value: Any):
        if key == 'theme':
            self.store.state['theme'] = value
        elif key == 'window_geometry':
            self.store.state['windowGeometry'] = value
        else:
            self.store.state[key] = value

    def get_option(self, key: str, default=None):
        return (self.store.state.get('generatorOptions') or {}).get(key, default)

    def set_option(self, key: str, value: Any):
        options = dict(self.store.state.get('generatorOptions') or {})
        options[key] = value
        self.store.state['generatorOptions'] = options
