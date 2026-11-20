"""Day/Night themes module following Material Design 3 guidelines.
Модуль тем День/Ніч у дусі Material Design 3."""

import json
import math
from pathlib import Path

# Supported modes / Підтримувані режими
MODES = ('day', 'night', 'system')

# Metrics and type scale / Метрики та шкала шрифтів
METRICS = {
    "space_xs": 4,
    "space_s": 8,
    "space_m": 16,
    "space_l": 24,
    "space_xl": 32,
    "button_height": 44,
    "min_target": 32,
    "corner": 8,
}

TYPE_SCALE = {
    "label": 11,
    "body": 12,
    "title": 15,
    "headline": 20,
}

# Palettes definitions / Визначення палітр
_DAY_PALETTE = {
    "bg": "#f8f9fa",
    "surface": "#ffffff",
    "surface_alt": "#f1f3f5",
    "on_bg": "#1a1d20",
    "on_surface": "#1a1d20",
    "muted": "#596573",
    "primary": "#0b57d0",
    "on_primary": "#ffffff",
    "outline": "#74777f",
    "focus": "#0b57d0",
    "error": "#b3261e",
    "on_error": "#ffffff",
    "success": "#146c43",
    "warning": "#b08800",
    "danger_btn": "#b3261e",
    "on_danger_btn": "#ffffff",
}

_NIGHT_PALETTE = {
    "bg": "#111315",
    "surface": "#1b1d20",
    "surface_alt": "#25282c",
    "on_surface": "#e3e3e8",
    "on_bg": "#e3e3e8",
    "muted": "#c4c7c5",
    "primary": "#a8c7fa",
    "on_primary": "#0842a0",
    "outline": "#8e9099",
    "focus": "#a8c7fa",
    "error": "#f2b8b5",
    "on_error": "#601410",
    "success": "#75fb4c",
    "warning": "#fde293",
    "danger_btn": "#f2b8b5",
    "on_danger_btn": "#601410",
}


def palette(name: str) -> dict:
    """Return a copy of the palette for the given name.
    Повертає копію палітри для заданого імені."""
    if name == 'day':
        return dict(_DAY_PALETTE)
    elif name == 'night':
        return dict(_NIGHT_PALETTE)
    else:
        raise KeyError(f"Unknown palette name: {name}")


def _hex_to_rgb(hex_str: str) -> tuple[float, float, float]:
    """Convert hex string (#rrggbb) to linear RGB components.
    Конвертує шістнадцятковий рядок у лінійні RGB компоненти."""
    hex_str = hex_str.lstrip('#')
    r = int(hex_str[0:2], 16) / 255.0
    g = int(hex_str[2:4], 16) / 255.0
    b = int(hex_str[4:6], 16) / 255.0
    
    def linearize(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        
    return linearize(r), linearize(g), linearize(b)


def luminance(hex_color: str) -> float:
    """Calculate WCAG 2 relative luminance.
    Обчислює відносну яскравість за WCAG 2."""
    r, g, b = _hex_to_rgb(hex_color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(color_a: str, color_b: str) -> float:
    """Calculate WCAG 2 contrast ratio between two colors.
    Обчислює коефіцієнт контрастності WCAG 2 між двома кольорами."""
    lum_a = luminance(color_a)
    lum_b = luminance(color_b)
    lighter = max(lum_a, lum_b)
    darker = min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def mode_label(mode: str, lang: str = 'en') -> str:
    """Return localized label for a UI theme mode.
    Повертає локалізовану мітку для режиму теми."""
    labels = {
        'day': {'uk': 'День', 'en': 'Day'},
        'night': {'uk': 'Ніч', 'en': 'Night'},
        'system': {'uk': 'Як у Windows', 'en': 'As in Windows'},
    }
    mode_dict = labels.get(mode, labels['system'])
    return mode_dict.get(lang, mode_dict['en'])


def read_windows_light() -> bool:
    """Read AppsUseLightTheme from Windows registry using winreg.
    Читає AppsUseLightTheme з реєстру Windows за допомогою winreg."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return bool(value)
    except Exception:
        raise OSError("Failed to read Windows registry theme preference")


def resolve(mode: str, read_windows_light=read_windows_light) -> str:
    """Resolve theme mode ('day' or 'night') considering system preferences.
    Визначає режим теми ('day' або 'night') з урахуванням системних налаштувань."""
    if mode not in MODES:
        mode = 'system'
        
    if mode == 'system':
        try:
            is_light = read_windows_light()
            return 'day' if is_light else 'night'
        except Exception:
            return 'night'
            
    return mode


def load_mode(path: Path) -> str:
    """Load theme mode from JSON settings file.
    Завантажує режим теми з JSON-файлу налаштувань."""
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
            theme = data.get('theme')
            if theme in MODES:
                return theme
    except Exception:
        pass
    return 'system'


def save_mode(path: Path, mode: str) -> None:
    """Save theme mode to JSON settings file, preserving other keys atomically.
    Зберігає режим теми до JSON-файлу налаштувань, зберігаючи інші ключі атомарно."""
    if mode not in MODES:
        raise ValueError(f"Invalid theme mode: {mode}")
        
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {}
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                data = {}
    except Exception:
        data = {}
        
    data['theme'] = mode
    
    import tempfile
    import os
    folder = path.parent
    fd, tmp = tempfile.mkstemp(dir=str(folder))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
