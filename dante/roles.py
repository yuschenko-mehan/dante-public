"""Roles management and installation logic / Керування ролями та логіка встановлення."""

import json
import time
from pathlib import Path

ROLES_FILE = Path(__file__).parent / "roles.json"

def validate(data):
    """Validate roles data structure / Перевірити структуру даних ролей."""
    errors = []
    if not isinstance(data, dict):
        return ["Data must be a dictionary / Дані мають бути словником"]
    
    roles = data.get("roles")
    if not isinstance(roles, list) or not roles:
        return ["Roles must be a non-empty list / Ролі мають бути не порожнім списком"]
    
    seen_ids = set()
    seen_orders = set()
    
    for i, role in enumerate(roles):
        if not isinstance(role, dict):
            errors.append(f"Role at index {i} is not a dict / Роль за індексом {i} не є словником")
            continue
            
        rid = role.get("id")
        if not isinstance(rid, str) or not rid.strip():
            errors.append(f"Role at index {i} has invalid id / Роль за індексом {i} має недійсний id")
        else:
            if rid in seen_ids:
                errors.append(f"Duplicate role id: {rid} / Дублікат id ролі: {rid}")
            seen_ids.add(rid)
            
        order = role.get("order")
        if not isinstance(order, int):
            errors.append(f"Role {rid} has invalid order / Роль {rid} має недійсний order")
        else:
            if order in seen_orders:
                errors.append(f"Duplicate role order: {order} / Дублікат order ролі: {order}")
            seen_orders.add(order)
            
        name = role.get("name")
        if not isinstance(name, dict) or not name.get("uk") or not name.get("en"):
            errors.append(f"Role {rid} missing uk or en name / Роль {rid} не має імені uk або en")
            
        summary = role.get("summary")
        if not isinstance(summary, dict) or not summary.get("uk") or not summary.get("en"):
            errors.append(f"Role {rid} missing uk or en summary / Роль {rid} не має опису uk або en")
            
        needs = role.get("needs")
        if not isinstance(needs, list):
            errors.append(f"Role {rid} needs must be a list / Потреби ролі {rid} мають бути списком")
            
        components = role.get("components")
        if not isinstance(components, list) or not components:
            errors.append(f"Role {rid} components must be a non-empty list / Компоненти ролі {rid} мають бути не порожнім списком")
            
    return errors

def load_roles(path=None):
    """Load and validate roles from file / Завантажити та перевірити ролі з файлу."""
    if path is None:
        path = ROLES_FILE
    else:
        path = Path(path)
        
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    errs = validate(data)
    if errs:
        raise ValueError(f"Invalid roles data: {errs} / Недійсні дані ролей: {errs}")
    
    # Sort roles by order / Сортувати ролі за порядком
    sorted_roles = sorted(data["roles"], key=lambda r: r.get("order", 0))
    data["roles"] = sorted_roles
    return data

def role_ids():
    """Return list of all role IDs / Повернути список усіх ідентифікаторів ролей."""
    data = load_roles()
    return [r["id"] for r in data["roles"]]

def _get_role_dict(rid):
    """Get role dictionary by ID / Отримати словник ролі за ID."""
    data = load_roles()
    for r in data["roles"]:
        if r["id"] == rid:
            return r
    raise KeyError(f"Unknown role ID: {rid} / Невідомий ID ролі: {rid}")

def get_role(rid):
    """Get role dictionary or raise KeyError / Отримати словник ролі або викликати KeyError."""
    return _get_role_dict(rid)

def name(rid, lang):
    """Get role name in given language / Отримати назву ролі заданою мовою."""
    r = _get_role_dict(rid)
    if lang not in ("uk", "en"):
        lang = "en"
    return r["name"].get(lang, r["name"]["en"])

def summary(rid, lang):
    """Get role summary in given language / Отримати опис ролі заданою мовою."""
    r = _get_role_dict(rid)
    if lang not in ("uk", "en"):
        lang = "en"
    return r["summary"].get(lang, r["summary"]["en"])

def components(rid):
    """Get role components list / Отримати список компонентів ролі."""
    r = _get_role_dict(rid)
    return r["components"]

def needs(rid):
    """Get role needs list / Отримати список потреб ролі."""
    r = _get_role_dict(rid)
    return r["needs"]

def menu_text(lang):
    """Generate installation menu text / Сформувати текст меню встановлення."""
    if lang != "uk":
        lang = "en"
        
    data = load_roles()
    if lang == "uk":
        lines = ["Який Данте встановити?"]
    else:
        lines = ["Which DANTE to install?"]
        
    for r in data["roles"]:
        num = r["order"]
        r_name = name(r["id"], lang)
        r_sum = summary(r["id"], lang)
        lines.append(f"{num}. {r_name} — {r_sum}")
        
    return "\n".join(lines)

def parse_language(text):
    """Parse language choice / Розпарсити вибір мови."""
    if not isinstance(text, str):
        return None
    cleaned = text.strip().lower()
    if cleaned in ("1", "uk", "ua", "укр", "українська", "ukrainian"):
        return "uk"
    if cleaned in ("2", "en", "eng", "english", "англійська"):
        return "en"
    return None

def parse_choice(text):
    """Parse role choice / Розпарсити вибір ролі."""
    if not isinstance(text, str):
        return None
    cleaned = text.strip()
    if not cleaned:
        return None
        
    # Check if number / Перевірити, чи це число
    if cleaned.isdigit():
        num = int(cleaned)
        data = load_roles()
        for r in data["roles"]:
            if r["order"] == num:
                return r["id"]
        return None
        
    # Check by id or name / Перевірити за id або назвою
    cleaned_lower = cleaned.lower()
    data = load_roles()
    for r in data["roles"]:
        if r["id"].lower() == cleaned_lower:
            return r["id"]
        for lang in ("uk", "en"):
            if r["name"].get(lang, "").lower() == cleaned_lower:
                return r["id"]
                
    return None

def can_become(new, has_flash, swarm_exists):
    """Check if role can be assumed / Перевірити, чи можна зайняти роль."""
    # Will raise KeyError if unknown role / Викличе KeyError для невідомої ролі
    _get_role_dict(new)
    
    if new == "archant":
        if swarm_exists and not has_flash:
            return False
    return True

def save_role(path, rid, lang, now=None):
    """Save selected role configuration to file / Зберегти конфігурацію обраної ролі у файл."""
    # Ensure role is valid / Переконатися, що роль валідна
    _get_role_dict(rid)
    
    if now is None:
        now = int(time.time())
        
    p = Path(path)
    data = {
        "role": rid,
        "lang": lang,
        "since": now
    }
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

def load_role(path):
    """Load role configuration from file or return None / Зчитати конфігурацію ролі з файлу або повернути None."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        content = p.read_text(encoding="utf-8")
        data = json.loads(content)
        if not isinstance(data, dict):
            return None
        rid = data.get("role")
        lang = data.get("lang")
        since = data.get("since")
        
        if not rid or not lang or since is None:
            return None
            
        # Verify role exists / Перевірити, чи існує роль
        _get_role_dict(rid)
        if lang not in ("uk", "en"):
            return None
            
        return {"role": rid, "lang": lang, "since": since}
    except Exception:
        return None
