# Installing DANTE on a Windows PC

[Українська версія](INSTALL.uk.md)

## Requirements
- Windows 10 or 11 (64-bit).
- **Python 3.13**: from the Microsoft Store (search "Python 3.13") or https://www.python.org (tick **"Add python.exe to PATH"**).
- **Git** (for step undo): `winget install Git.Git`.
- Optional: Graphify (code map — faster, more accurate work): `python -m pip install --user graphifyy`.

## Install
1. Open **Releases** of this repository and download the newest `dante-<version>.zip` (or **Code → Download ZIP**).
2. Unzip it, e.g. to `C:\DANTE\dante`.
3. Double-click **`Dante.bat`** — the DANTE window opens.
4. Add at least one free model: **"+ Models"** (Ctrl+M) — see [docs/MODELS.md](MODELS.md).
5. Check: double-click **`selftest.bat`** — it should end with `RESULT: ALL PASSED`.

Tip: `python -m dante setup` shows which models (including offline local ones) fit your PC.

## Updates
- Check and install: `python -m dante update` (check), `python -m dante update install` (install), `python -m dante update rollback` (go back). A daily automatic check in the DANTE window comes in the next version.
- Safety: updates come **only** from this repository, are verified by SHA-256, and never overwrite your keys, settings, models or lessons.

## Murakha (work on several PCs)
Download `murakha-<version>-windows-x64.zip` from Releases, unzip on every PC and read `ПРОЧИТАЙ.txt`. Allow **Private networks** in the Windows firewall prompt.

## Uninstall
Delete the DANTE folder (and `keys.txt` in it, if you no longer need your keys).
