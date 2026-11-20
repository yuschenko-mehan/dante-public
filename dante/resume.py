import json
from pathlib import Path


def resume_interrupted(inbox, outbox, say=lambda m: None):
    inbox, outbox = Path(inbox), Path(outbox)
    out = []
    for mark in sorted(outbox.glob("*.running")):
        stem = mark.stem
        mark.unlink(missing_ok=True)
        if (outbox / f"{stem}.txt").exists():
            continue
        src = inbox / "done" / f"{stem}.json"
        if not src.exists():
            continue
        text = src.read_text(encoding="utf-8")
        if "-retry" in stem or "restart" in stem.lower() or "restart_pult" in text:
            (outbox / f"{stem}.txt").write_text("EXIT 125\nInterrupted (power or crash), not repeated / перервано, не повторено\n", encoding="utf-8")
            continue
        dst = inbox / f"{stem}-retry1.json"
        if not dst.exists():
            dst.write_text(text, encoding="utf-8")
        say(f"resumed / повторно в черзі: {stem}")
        out.append(stem)
    return out
