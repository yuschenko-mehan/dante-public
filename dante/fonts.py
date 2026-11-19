"""Drafting font for the whole DANTE window (GOST 2.304 / ISO 3098 style, slanted 75°).

Order of choice:
  1. ISOCPEUR (comes with AutoCAD; already slanted 75°) — used if installed, never copied.
  2. GOST type A / GOST type B (come with KOMPAS; slanted by design).
  3. OpenGost Type A TT — free (SIL OFL 1.1). Stored in DANTE\\fonts and loaded only for DANTE
     (nothing is installed into Windows). It is upright, so DANTE draws it slanted (italic ≈ 75°).
  4. Ordinary Windows font.

    python -m dante fonts      — show what is found; download OpenGost if no drafting font exists
"""

from __future__ import annotations

import io
import os
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "fonts"
OPENGOST_URLS = [  # same archive, several places (the author's old Bitbucket link may be gone)
    "https://api.opensuse.org/public/source/openSUSE:Factory/opengost-fonts/opengostfont-ttf-0.3.tar.xz",
    "https://api.opensuse.org/public/source/M17N:fonts/opengost-fonts/opengostfont-ttf-0.3.tar.xz",
    "https://bitbucket.org/fat_angel/opengostfont/downloads/opengostfont-ttf-0.3.tar.xz",
]
# (family name, needs extra slant)
CANDIDATES = [
    ("ISOCPEUR", False),
    ("GOST type A", False),
    ("GOST type B", False),
    ("GOST Type AU", False),
    ("OpenGost Type A TT", True),
    ("OpenGost Type B TT", True),
]
FALLBACK = [("Segoe UI Variable Text", False), ("Segoe UI", False), ("DejaVu Sans", False)]


def load_private_fonts(folder: Path = FONT_DIR) -> list[str]:
    """Windows: make the .ttf/.otf files in `folder` usable by this program only (FR_PRIVATE)."""
    loaded = []
    if os.name != "nt" or not folder.is_dir():
        return loaded
    import ctypes
    for f in sorted(folder.glob("*.[ot]tf")):
        if ctypes.windll.gdi32.AddFontResourceExW(str(f), 0x10, 0):
            loaded.append(f.name)
    return loaded


def choose(families: set[str], loaded_files: list[str] | None = None) -> tuple[str, bool]:
    """Pick the drafting font. `families` = installed families (from Tk)."""
    lower = {f.lower(): f for f in families}
    loaded = " ".join(loaded_files or []).lower()
    for name, slant in CANDIDATES:
        if name.lower() in lower:
            return lower[name.lower()], slant
        if name.startswith("OpenGost Type A") and "opengosttypea" in loaded:
            return name, slant
        if name.startswith("OpenGost Type B") and "opengosttypeb" in loaded:
            return name, slant
    for name, slant in FALLBACK:
        if name.lower() in lower:
            return lower[name.lower()], slant
    return "TkDefaultFont", False


def download_opengost(folder: Path = FONT_DIR, timeout: int = 60) -> str:
    """Download the free OpenGost TTF fonts (OFL 1.1) into DANTE\\fonts. Returns a message."""
    folder.mkdir(parents=True, exist_ok=True)
    last = ""
    for url in OPENGOST_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "DANTE"})
            data = urllib.request.urlopen(req, timeout=timeout).read()
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as tar:
                got = []
                for m in tar.getmembers():
                    name = Path(m.name).name
                    if m.isfile() and (name.lower().endswith(".ttf") or "license" in name.lower()
                                       or "ofl" in name.lower()):
                        src = tar.extractfile(m)
                        if src:
                            (folder / name).write_bytes(src.read())
                            got.append(name)
            if any(g.lower().endswith(".ttf") for g in got):
                return "downloaded: " + ", ".join(got)
            last = "no .ttf inside the archive"
        except Exception as e:  # report and try the next source
            last = f"{url}: {e}"
    return "NOT downloaded: " + last


def main() -> int:
    import tkinter as tk
    from tkinter import font
    r = tk.Tk()
    r.withdraw()
    fams = set(font.families(r))
    found = [n for n, _ in CANDIDATES if n.lower() in {f.lower() for f in fams}]
    print("Drafting fonts installed in Windows:", ", ".join(found) or "none")
    have_files = sorted(p.name for p in FONT_DIR.glob("*.[ot]tf")) if FONT_DIR.is_dir() else []
    if not found and not have_files:
        print("OpenGost:", download_opengost())
        have_files = sorted(p.name for p in FONT_DIR.glob("*.[ot]tf")) if FONT_DIR.is_dir() else []
    print("Font files in DANTE\\fonts:", ", ".join(have_files) or "none")
    loaded = load_private_fonts()
    fam, slant = choose(set(font.families(r)), loaded)
    print("DANTE will use:", fam, "(drawn slanted)" if slant else "")
    r.destroy()
    return 0
