from typing import Callable, Dict, List

from klotto.config import THEMES
from klotto.logging import logger


def _widget_styles(theme: Dict[str, str]) -> str:
    return f"""
        QWidget {{
            background-color: {theme['bg_primary']};
            font-family: 'Malgun Gothic', 'Segoe UI', sans-serif;
            color: {theme['text_primary']};
        }}

        QGroupBox {{
            background-color: {theme['bg_secondary']};
            border: 1px solid {theme['border']};
            border-radius: 12px;
            margin-top: 12px;
            padding-top: 8px;
            font-size: 15px;
            font-weight: bold;
            color: {theme['text_primary']};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 2px 12px;
            left: 12px;
            background-color: {theme['accent']};
            color: white;
            border-radius: 4px;
        }}
    """


def _input_styles(theme: Dict[str, str]) -> str:
    return f"""
        QLineEdit, QSpinBox {{
            border: 1px solid {theme['border']};
            border-radius: 8px;
            padding: 4px 12px;
            background-color: {theme['bg_secondary']};
            color: {theme['text_primary']};
            font-size: 14px;
            selection-background-color: {theme['accent']};
        }}
        QLineEdit:focus, QSpinBox:focus {{
            border: 2px solid {theme['accent']};
            background-color: {theme['bg_primary']};
        }}
        QLineEdit:hover, QSpinBox:hover {{
            border-color: {theme['accent']};
        }}
        QSpinBox::up-button, QSpinBox::down-button {{
            width: 20px;
            border: none;
            background-color: {theme['bg_tertiary']};
        }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
            background-color: {theme['accent']};
        }}
    """


def _checkbox_styles(theme: Dict[str, str]) -> str:
    return f"""
        QCheckBox {{
            spacing: 10px;
            font-size: 14px;
            color: {theme['text_secondary']};
            font-weight: 600;
        }}
        QCheckBox::indicator {{
            width: 20px;
            height: 20px;
            border: 2px solid {theme['border']};
            border-radius: 5px;
            background-color: {theme['bg_secondary']};
        }}
        QCheckBox::indicator:hover {{
            border-color: {theme['accent']};
            background-color: {theme['accent_light']};
        }}
        QCheckBox::indicator:checked {{
            background-color: {theme['accent']};
            border-color: {theme['accent']};
            image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMiIgaGVpZ2h0PSIxMiIgdmlld0JveD0iMCAwIDEyIDEyIj48cGF0aCBmaWxsPSJ3aGl0ZSIgZD0iTTEwIDNMNC41IDguNSAyIDYiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgZmlsbD0ibm9uZSIvPjwvc3ZnPg==);
        }}
    """


def _scroll_styles(theme: Dict[str, str]) -> str:
    return f"""
        QScrollArea {{
            background-color: {theme['bg_secondary']};
            border: 1px solid {theme['border']};
            border-radius: 12px;
        }}
        QScrollBar:vertical {{
            background-color: {theme['bg_tertiary']};
            width: 10px;
            border-radius: 5px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {theme['neutral']};
            border-radius: 4px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {theme['accent']};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
    """


def _button_styles(theme: Dict[str, str], is_dark: bool) -> str:
    clear_hover = "#8B9AAB" if not is_dark else "#7C8A9A"
    return f"""
        QPushButton {{
            border-radius: 8px;
            font-size: 15px;
            font-weight: bold;
            color: #FFFFFF;
            border: none;
            padding: 10px 18px;
        }}

        QPushButton#generateBtn {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {theme['accent']}, stop:1 {theme['accent_hover']});
        }}
        QPushButton#generateBtn:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {theme['accent_hover']}, stop:1 {theme['accent']});
        }}
        QPushButton#generateBtn:pressed {{
            background-color: {theme['accent_hover']};
            padding-top: 12px;
            padding-bottom: 8px;
        }}

        QPushButton#clearBtn {{
            background-color: {theme['neutral']};
        }}
        QPushButton#clearBtn:hover {{
            background-color: {clear_hover};
        }}

        QPushButton#saveBtn {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {theme['success']}, stop:1 #1E8449);
        }}
        QPushButton#saveBtn:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #1E8449, stop:1 {theme['success']});
        }}

        QPushButton#copyBtn {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {theme['warning']}, stop:1 #D68910);
        }}
        QPushButton#copyBtn:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #D68910, stop:1 {theme['warning']});
        }}

        QPushButton:disabled {{
            background-color: {theme['bg_tertiary']};
            color: {theme['text_muted']};
        }}
    """


def _utility_styles(theme: Dict[str, str]) -> str:
    return f"""
        QStatusBar {{
            background-color: {theme['bg_secondary']};
            color: {theme['text_secondary']};
            border-top: 1px solid {theme['border']};
            padding: 4px 8px;
            font-size: 13px;
        }}

        QToolTip {{
            background-color: {theme['bg_tertiary']};
            color: {theme['text_primary']};
            border: 1px solid {theme['border']};
            padding: 6px 10px;
            border-radius: 6px;
            font-size: 13px;
        }}

        QFrame#infoContainer {{
            background-color: {theme['card_bg']};
            border: 1px solid {theme['border']};
            border-radius: 12px;
        }}

        QLabel#placeholderLabel {{
            color: {theme['text_muted']};
            font-size: 15px;
            padding: 50px;
            font-style: italic;
        }}

        QDialog {{
            background-color: {theme['bg_primary']};
        }}

        QListWidget {{
            background-color: {theme['bg_secondary']};
            border: 1px solid {theme['border']};
            border-radius: 8px;
            padding: 4px;
            outline: none;
        }}
        QListWidget::item {{
            padding: 10px 12px;
            border-radius: 6px;
            margin: 2px;
        }}
        QListWidget::item:hover {{
            background-color: {theme['bg_hover']};
        }}
        QListWidget::item:selected {{
            background-color: {theme['accent_light']};
            color: {theme['accent']};
        }}
    """


class ThemeManager:
    """Manage the shared application theme."""

    _current_theme = "light"
    _listeners: List[Callable[[], None]] = []

    @classmethod
    def get_theme(cls) -> Dict:
        return THEMES[cls._current_theme]

    @classmethod
    def get_theme_name(cls) -> str:
        return cls._current_theme

    @classmethod
    def toggle_theme(cls):
        cls._current_theme = "dark" if cls._current_theme == "light" else "light"
        logger.info("Theme changed to: %s", cls._current_theme)
        for listener in list(cls._listeners):
            listener()

    @classmethod
    def add_listener(cls, callback: Callable[[], None]):
        if callback not in cls._listeners:
            cls._listeners.append(callback)

    @classmethod
    def get_stylesheet(cls) -> str:
        theme = cls.get_theme()
        is_dark = cls._current_theme == "dark"
        return "\n".join(
            (
                _widget_styles(theme),
                _input_styles(theme),
                _checkbox_styles(theme),
                _scroll_styles(theme),
                _button_styles(theme, is_dark),
                _utility_styles(theme),
            )
        )


__all__ = ["ThemeManager"]
