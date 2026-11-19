"""Specification for dante/models_hub.py — the list of user-added AI models.

models.json holds {"models": [entry, ...]}. An entry:
  name      str  ^[a-z0-9][a-z0-9-]{1,30}$   unique, not one of the built-ins
            (BUILTIN_NAMES = frozenset of dante.config.DEFAULT_PROVIDERS names)
  base_url  str  https://...  or  http://localhost|127.0.0.1[:port]/...
  model     str  1..120 chars, no spaces at the ends, no newlines
  key_env   str  ^[A-Z][A-Z0-9_]{2,40}$   required when needs_key is true, else may be ""
  needs_key bool
  paid      bool
  price_in  float >= 0   (USD per 1M input tokens), required > 0 when paid
  price_out float >= 0   required > 0 when paid
  note      str  optional, <= 200 chars
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from dante.config import DEFAULT_PROVIDERS

BUILTIN_NAMES: frozenset[str] = frozenset(p.name for p in DEFAULT_PROVIDERS)

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
KEY_ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,40}$")
# optional fields: filled in when missing (Claude's review fix)
DEFAULTS = {"key_env": "", "needs_key": True, "paid": False, "price_in": 0.0, "price_out": 0.0, "note": ""}


def validate(entry: dict, taken: set[str]) -> list[str]:
    """Validate a model entry dictionary. Return a list of invalid field names."""
    errors: list[str] = []

    if not isinstance(entry, dict):
        # If entry is not even a dict, report common expected fields or arbitrary identifier
        return ["name", "base_url", "model", "key_env", "needs_key", "paid", "price_in", "price_out", "note"]

    # name: str, pattern, unique, not builtin
    name = entry.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name) or name in BUILTIN_NAMES or name in taken:
        errors.append("name")

    # base_url: str, https://... or http://localhost|127.0.0.1[:port]/...
    base_url = entry.get("base_url")
    if not isinstance(base_url, str):
        errors.append("base_url")
    else:
        try:
            parsed = urlparse(base_url)
            scheme = parsed.scheme
            netloc = parsed.netloc
            path = parsed.path

            valid_scheme = scheme in ("http", "https")
            if not valid_scheme:
                errors.append("base_url")
            else:
                # Check host/port and general constraints
                if not netloc or parsed.query or parsed.fragment or parsed.username or parsed.password:
                    errors.append("base_url")
                else:
                    host = parsed.hostname
                    if scheme == "https":
                        if not host or " " in base_url:
                            errors.append("base_url")
                    elif scheme == "http":
                        if host not in ("localhost", "127.0.0.1"):
                            errors.append("base_url")
                        elif not host or " " in base_url:
                            errors.append("base_url")
        except Exception:
            errors.append("base_url")

    # model: str, 1..120 chars, no spaces at ends, no newlines
    model = entry.get("model")
    if not isinstance(model, str) or not (1 <= len(model) <= 120) or model.startswith(" ") or model.endswith(" ") or "\n" in model:
        errors.append("model")

    # needs_key: bool
    needs_key = entry.get("needs_key")
    if not isinstance(needs_key, bool):
        errors.append("needs_key")

    # key_env: str, pattern, required when needs_key is true, else may be ""
    key_env = entry.get("key_env")
    if not isinstance(key_env, str):
        errors.append("key_env")
    else:
        if needs_key:
            if not KEY_ENV_RE.match(key_env):
                errors.append("key_env")
        else:
            if key_env != "" and not KEY_ENV_RE.match(key_env):
                errors.append("key_env")

    # paid: bool
    paid = entry.get("paid")
    if not isinstance(paid, bool):
        errors.append("paid")

    # price_in: float >= 0, required > 0 when paid
    price_in = entry.get("price_in")
    if isinstance(price_in, bool) or not isinstance(price_in, (int, float)):
        errors.append("price_in")
    else:
        p_in = float(price_in)
        if not math.isfinite(p_in) or p_in < 0 or (paid and p_in <= 0):
            errors.append("price_in")

    # price_out: float >= 0, required > 0 when paid
    price_out = entry.get("price_out")
    if isinstance(price_out, bool) or not isinstance(price_out, (int, float)):
        errors.append("price_out")
    else:
        p_out = float(price_out)
        if not math.isfinite(p_out) or p_out < 0 or (paid and p_out <= 0):
            errors.append("price_out")

    # note: str, optional, <= 200 chars
    note = entry.get("note")
    if note is not None:
        if not isinstance(note, str) or len(note) > 200:
            errors.append("note")

    return errors


def load(path: str | Path) -> list[dict]:
    """Load models from json file. Missing or invalid file returns []. Skips invalid entries."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        if not isinstance(data, dict) or "models" not in data or not isinstance(data["models"], list):
            return []
        
        valid_models = []
        taken: set[str] = set()
        for item in data["models"]:
            if not isinstance(item, dict):
                continue
            item = {**DEFAULTS, **item}
            # Temporarily check validation against taken names so far in the file
            errs = validate(item, taken)
            if not errs:
                name = item.get("name")
                if isinstance(name, str):
                    taken.add(name)
                    valid_models.append(item)
        return valid_models
    except Exception:
        return []


def save(path: str | Path, entries: list[dict]) -> None:
    """Save models atomically to path using a temp file in the same folder and os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {"models": entries}
    content = json.dumps(data, indent=2)

    fd, temp_path_str = tempfile.mkstemp(dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(temp_path_str, path)
    finally:
        if os.path.exists(temp_path_str):
            try:
                os.remove(temp_path_str)
            except OSError:
                pass


def upsert(path: str | Path, entry: dict) -> None:
    """Upsert a model entry. Fills defaults if missing, validates, raises ValueError if invalid."""
    full_entry = dict(DEFAULTS)
    full_entry.update(entry)

    # Validate with other existing models' names as taken
    existing = load(path)
    taken = {m["name"] for m in existing if isinstance(m, dict) and "name" in m}
    # If updating an existing model, its name shouldn't conflict with itself
    name = full_entry.get("name")
    if name in taken:
        taken.remove(name)

    errs = validate(full_entry, taken)
    if errs:
        raise ValueError(f"Invalid model entry, errors in fields: {', '.join(errs)}")

    # Update or append
    updated_entries = []
    found = False
    for m in existing:
        if isinstance(m, dict) and m.get("name") == name:
            updated_entries.append(full_entry)
            found = True
        else:
            updated_entries.append(m)
    if not found:
        updated_entries.append(full_entry)

    save(path, updated_entries)


def remove(path: str | Path, name: str) -> bool:
    """Remove a model by name. Returns True if removed, False if not found."""
    existing = load(path)
    new_entries = [m for m in existing if isinstance(m, dict) and m.get("name") != name]
    if len(new_entries) == len(existing):
        return False
    save(path, new_entries)
    return True


def set_key(path: str | Path, env_name: str, value: str) -> None:
    """Set an environment key in keys.txt-like file. Validates key name and value.

    Never puts a key value into an error message.
    """
    if not isinstance(env_name, str) or not KEY_ENV_RE.match(env_name):
        raise ValueError("Invalid environment variable name")

    if not isinstance(value, str):
        raise ValueError("Key value must be a string")

    stripped_value = value.strip()
    if not stripped_value or any(c.isspace() for c in stripped_value):
        raise ValueError("Invalid key value format")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    if path.exists():
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()

    found = False
    new_lines = []
    for line in lines:
        stripped_line = line.strip()
        if stripped_line and not stripped_line.startswith("#") and "=" in stripped_line:
            name_part, _, _ = stripped_line.partition("=")
            if name_part.strip() == env_name:
                new_lines.append(f"{env_name}={stripped_value}")
                found = True
                continue
        new_lines.append(line)

    if not found:
        new_lines.append(f"{env_name}={stripped_value}")

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def has_key(path: str | Path, env_name: str) -> bool:
    """Check if keys file has a non-empty value for the given environment name."""
    path = Path(path)
    if not path.exists():
        return False
    try:
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() == env_name:
                val = value.strip().strip('"').strip("'")
                return bool(val)
    except Exception:
        pass
    return False

