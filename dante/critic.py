"""Critic utilities.
Критичні утиліти.
"""

import json
import re

def critic_prompt(task, diff):
    """Create a prompt that asks for a JSON with score and issues.
    The prompt contains the task, the diff and explicitly mentions the words
    "score", "issues" and "JSON".
    Створює підказку, яка просить JSON з полями score і issues. Підказка містить завдання, diff і слова "score", "issues", "JSON".
    """
    return (
        f"Task: {task}\n"
        f"Diff:\n{diff}\n"
        "Please provide ONLY a JSON object with keys \"score\" (0-10) and \"issues\" (list of strings). "
        "The response must be valid JSON. Include the words score, issues and JSON in your answer."
    )

def _extract_first_json(text):
    """Extract the first {...} substring that looks like JSON.
    Returns the substring or None.
    Витягує перший підрядок {...}, який виглядає як JSON.
    """
    match = re.search(r'\{.*?\}', text, re.DOTALL)
    return match.group(0) if match else None

def parse_critic(text):
    """Parse critic output into a dict with score and issues.
    Handles malformed input gracefully.
    Розбирає вихід критика у словник з полями score і issues, обробляючи помилки.
    """
    json_str = _extract_first_json(text)
    if not json_str:
        return {"score": 0.0, "issues": ["critic answer unreadable"]}

    try:
        data = json.loads(json_str)
    except Exception:
        return {"score": 0.0, "issues": ["critic answer unreadable"]}

    # score handling
    raw_score = data.get("score", 0)
    try:
        score = float(raw_score)
    except Exception:
        score = 0.0
    score = max(0.0, min(10.0, score))

    # issues handling
    raw_issues = data.get("issues", [])
    issues = []
    if isinstance(raw_issues, list):
        for item in raw_issues:
            if isinstance(item, str):
                issues.append(item)
    # ensure at least empty list
    return {"score": score, "issues": issues}

def rank_solutions(cands):
    """Rank solutions according to spec.
    Order: passed first, higher score, fewer lines, fewer warnings, alphabetical model.
    Ранжує рішення згідно специфікації.
    """
    def sort_key(c):
        return (
            not c.get("passed", False),          # False (passed) comes first
            -c.get("score", 0),                  # higher score first
            c.get("lines", 0),                   # fewer lines first
            c.get("warnings", 0),                # fewer warnings first
            c.get("model", "")                   # alphabetical
        )
    return sorted(cands, key=sort_key)

def best(cands):
    """Return the best passed candidate or None.
    Returns the first passed candidate after ranking, or None if none passed.
    Повертає найкращий пройшений кандидат або None.
    """
    ranked = rank_solutions(cands)
    for cand in ranked:
        if cand.get("passed"):
            return cand
    return None
