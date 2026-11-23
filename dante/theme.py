"""Theme palette generation: Campbell colors, dark/light modes, and accessibility contrast.
Генерація палітри тем: кольори Кампбелл, темний/світлий режими та контрастність для доступності.
"""

from __future__ import annotations

from dante import ui_theme

CAMPBELL = {
    "black": "#0c0c0c",
    "dark_blue": "#0037da",
    "dark_green": "#13a10e",
    "dark_cyan": "#3a96dd",
    "dark_red": "#c50f1f",
    "dark_magenta": "#881798",
    "dark_yellow": "#c19c00",
    "gray": "#767676",
    "dark_gray": "#333333",
    "blue": "#3b78ff",
    "green": "#16c60c",
    "cyan": "#61d6d6",
    "red": "#e74856",
    "magenta": "#b4009e",
    "yellow": "#f9f1a5",
    "white": "#f2f2f2",
}


def step(current: int, delta: int) -> int:
    """Move the contrast step (0..100) / Змінити крок контрасту (0..100)."""
    return max(0, min(100, current + delta))


def value_from_x(x: int, width: int) -> int:
    """Calculate contrast percentage from slider x coordinate / Обчислити відсоток контрасту за координатою x."""
    if width <= 1:
        return 0
    return int(max(0, min(100, (x / (width - 1)) * 100)))


def x_from_value(value: int, width: int) -> int:
    """Calculate slider x coordinate from contrast percentage / Обчислити координату x за відсотком контрасту."""
    return int((max(0, min(100, value)) / 100) * (width - 1))


def contrast_ratio(c1: str, c2: str) -> float:
    """Calculate WCAG contrast ratio between two hex colors / Обчислити коефіцієнт контрастності WCAG між двома кольорами."""
    return ui_theme.contrast(c1, c2)


def palette(level: int) -> dict[str, str]:
    """Generate the dark (night) palette for the given contrast level (0..100) / Згенерувати темну (нічну) палітру для заданого рівня контрасту (0..100)."""
    level = max(0, min(100, level))
    
    # Background gets darker as level decreases (down to #000000 at level 0)
    # Фонон стає темнішим із зменшенням рівня (до #000000 на рівні 0)
    bg_val = int(12 + (level / 100) * 8) if level > 0 else 0
    bg = f"#{bg_val:02x}{bg_val:02x}{bg_val:02x}"
    
    surf_val = bg_val + int(12 + (level / 100) * 15)
    surf = f"#{surf_val:02x}{surf_val:02x}{surf_val:02x}"
    
    alt_val = surf_val + int(8 + (level / 100) * 10)
    surf_alt = f"#{alt_val:02x}{alt_val:02x}{alt_val:02x}"
    
    border_val = alt_val + int(20 + (level / 100) * 30)
    border = f"#{border_val:02x}{border_val:02x}{border_val:02x}"
    
    fg_val = int(180 + (level / 100) * 75)
    fg = f"#{fg_val:02x}{fg_val:02x}{fg_val:02x}"
    
    fg2_val = int(120 + (level / 100) * 60)
    fg2 = f"#{fg2_val:02x}{fg2_val:02x}{fg2_val:02x}"

    return {
        "BG": bg,
        "SURFACE": surf,
        "SURFACE2": surf_alt,
        "HOVER": border,
        "BORDER": border,
        "FG": fg,
        "FG2": fg2,
        "LOG_BG": bg,
        "LOG_FG": fg,
        "ACCENT": CAMPBELL["cyan"],
        "WARN": CAMPBELL["dark_yellow"],
        "ERR": CAMPBELL["dark_red"],
        "OK": CAMPBELL["dark_green"],
    }


def palette_for(mode: str, level: int, read_windows_light=None) -> dict[str, str]:
    """Return palette for mode ('night', 'day', 'system'), level, and Windows light mode reader / Повернути палітру для режиму, рівня та зчитувача світлого режиму Windows."""
    if mode == "night":
        return palette(level)
    elif mode == "day":
        day_p = ui_theme.palette("day")
        return {
            "BG": day_p["bg"],
            "SURFACE": day_p["surface"],
            "SURFACE2": day_p["surface_alt"],
            "HOVER": day_p["surface_alt"],
            "BORDER": day_p["outline"],
            "FG": day_p["on_surface"],
            "FG2": day_p["muted"],
            "LOG_BG": day_p["surface"],
            "LOG_FG": day_p["on_surface"],
            "ACCENT": day_p["primary"],
            "WARN": day_p["warning"],
            "ERR": day_p["error"],
            "OK": day_p["success"],
        }
    elif mode == "system":
        checker = read_windows_light or ui_theme.read_windows_light
        is_light = checker()
        if is_light:
            return palette_for("day", level, read_windows_light)
        else:
            return palette(level)
    else:
        return palette(level)
