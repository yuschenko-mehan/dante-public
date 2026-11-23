"""DANTE self-test on the real computer: unit tests + the window driven by itself.

    python -m dante selftest          (results are printed; selftest.bat saves them to selftest.txt)

Uses only a temporary project and the author's settings are not touched (a temporary settings folder).
No models are called, nothing costs money.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_unit_tests() -> bool:
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=1).run(suite)
    return result.wasSuccessful()


def run_window_checks(show_seconds: float = 4.0) -> dict[str, bool]:
    tmp = Path(tempfile.mkdtemp(prefix="dante-selftest-"))
    os.environ["APPDATA"] = str(tmp / "appdata")  # own settings file, the author's one stays as it is
    proj = tmp / "proj"
    (proj / "tests").mkdir(parents=True)
    (proj / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (proj / "tests" / "test_calc.py").write_text(
        "import unittest\nfrom calc import add\n\nclass T(unittest.TestCase):\n"
        "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n", encoding="utf-8")

    from dante import gui
    from dante import gui_logic as L
    from dante.planner import Plan, Step

    w = gui.DanteWindow()
    r = w.root
    w.state.shortcut_done = True

    def pump(sec: float) -> None:
        end = time.time() + sec
        while time.time() < end:
            r.update()
            time.sleep(0.05)

    def wait_done(limit: float = 30) -> None:
        end = time.time() + limit
        while time.time() < end and w.proc and w.proc.poll() is None:
            pump(0.2)
        pump(0.5)

    log = lambda: w.log.get("1.0", "end")  # noqa: E731
    py = f'"{sys.executable}"'
    res: dict[str, bool] = {}
    pump(1)
    title = r.title()
    res["window opens, version shown"] = "DANTE" in title and ("build" in title or "збірка" in title)
    w.start("run")
    res["asks for project first"] = "⚠" in log()
    w.project.set(str(proj))
    w.test.set(f"{py} -m unittest discover -s tests")
    w.run_tests()
    wait_done()
    res["tests button runs project tests"] = "OK" in log() and w.status_key == "done"
    w.show_help()
    w.wallet()
    pump(0.3)
    res["help with hotkeys"] = "Ctrl+Alt+Q" in log()
    res["wallet shows spending"] = "$" in log() or "₴" in log() or "грн" in log()
    if os.name == "nt":
        if w.another:  # the author's own DANTE window is open and holds the keys: that is correct
            res["global hotkeys (held by the open DANTE window)"] = True
        elif any(x in log() for x in ("зайняті", "already used")):
            import re
            import subprocess
            busy = re.findall(r"(?:зайняті іншою програмою|already used by another program): (.*)", log())
            tl = subprocess.run(["tasklist"], capture_output=True, text=True, errors="replace").stdout.lower()
            print("  busy keys:", busy[-1] if busy else "?")
            print("  python processes:", sorted({ln.split()[0] for ln in tl.splitlines() if ln.startswith("python")}))
            # an older DANTE window (started with pythonw) holds the keys: correct; otherwise a real conflict
            res["global hotkeys (held by an open DANTE window)"] = "pythonw" in tl
        else:
            res["global hotkeys registered"] = True
    w.test.set(f'{py} -c "import time; time.sleep(60)"')
    w.run_tests()
    pump(1.5)
    w.stop()
    pump(2)
    res["STOP ends a running job"] = w.status_key == "stopped" and w.proc.poll() is not None
    w.lang_box.set("English")
    w.change_language()
    pump(0.5)
    res["English language"] = r.title().startswith("DANTE Architect")
    Plan("g", "s", [Step(1, "a", "b", [], f"{py} -c 1")]).save(proj)
    w.start("approve")
    wait_done()
    res["approve plan button"] = w.status_key == "done" and Plan.load(proj).approved
    w.lang_box.set("Українська")
    w.change_language()
    pump(0.5)
    from dante.theme import contrast_ratio
    w.theme_mode = "night"   # the contrast knob belongs to the night theme / крутилка контрасту — для нічної теми
    w.slider.set(0, now=True)
    pump(0.5)
    dark = (w.P["LOG_BG"], contrast_ratio(w.P["LOG_FG"], w.P["LOG_BG"]), w.log.cget("bg"))
    w.slider.set(100, now=True)
    pump(0.5)
    bright = contrast_ratio(w.P["LOG_FG"], w.P["LOG_BG"])
    res["contrast slider: 0 = darkest, 100 = brightest"] = (dark[0] == "#000000" and dark[2] == "#000000"
                                                           and dark[1] >= 3 and bright >= 12
                                                           and L.load_state().contrast == 100)
    res["slider recolours live (log kept)"] = "Ctrl+Alt+Q" in log() and w.log.cget("bg") == w.P["LOG_BG"]
    w.slider.set(gui.DEFAULT_CONTRAST, now=True)
    pump(0.5)
    res["drafting font chosen"] = bool(w.font)
    print("  font in use:", w.font, "(slanted by DANTE)" if w.slant else "")
    res["back to Ukrainian, settings saved"] = r.title().startswith("Архітектор Данте") and L.load_state().lang == "uk"
    # the "AI models" form: add a local model, it appears in the settings, then delete it
    from dante import config, gui_github, gui_models, models_hub
    mpath, kpath = tmp / "models.json", tmp / "keys.txt"
    mw = gui_models.ModelsWindow(w, models_path=mpath, keys_path=kpath)
    pump(0.5)
    n_builtin = mw.lst.size()
    mw.preset_box.set(mw.preset_box.cget("values")[1])  # Ollama on this PC
    mw.apply_preset()
    mw.model.set("qwen2.5-coder:1.5b")
    pump(0.3)
    auto = mw.name.get()
    mw.save()
    pump(0.3)
    s2 = config.load_settings(tmp / "none.toml", mpath)
    res["models form: add a model in a few clicks"] = (
        auto == "ollama-qwen2-5-coder-1-5b" and mw.lst.size() == n_builtin + 1
        and auto in s2.order and models_hub.load(mpath)[0]["needs_key"] is False)
    mw.new()
    mw.preset_box.set(mw.preset_box.cget("values")[7])  # Cerebras: needs a key
    mw.apply_preset()
    mw.model.set("some-model")
    no_key = mw.save() is False and "ключ" in mw.status.cget("text").lower()
    mw.key.set("test-key-123")
    saved = mw.save()
    res["models form: key goes to keys.txt only"] = (no_key and saved and models_hub.has_key(kpath, "CEREBRAS_API_KEY")
                                                    and "test-key-123" not in mpath.read_text(encoding="utf-8")
                                                    and "test-key-123" not in log())
    mw.paid.set(1)
    mw.paid_changed()
    mw.check()
    res["models form: paid model is never pinged"] = "платна" in mw.status.cget("text").lower()
    pump(show_seconds / 3)
    mw.close()
    # GitHub window: opens, shows tool status, keeps options; no new repository without the author's yes
    # Вікно GitHub: відкривається, показує стан, зберігає вибір; без «так» автора нового репозиторію немає
    gw = gui_github.GithubWindow(w)
    end = time.time() + 40
    while time.time() < end and "…" in gw.marks["acc"].cget("text"):
        pump(0.3)
    gw.auto.set(1)
    gw.save_opts()
    res["github window: status shown, options saved"] = ("…" not in gw.marks["git"].cget("text")
                                                         and L.load_state().github_auto)
    w.publish(ask=False)
    pump(0.3)
    res["github: no new repository without confirmation"] = (
        ("ще не викладено" in log() or "not published yet" in log()) and w.status_key != "working")
    gw.auto.set(0)
    gw.save_opts()
    gw.win.destroy()
    w.test.set(f"{py} -m unittest discover -s tests")
    w.task.delete("1.0", "end")
    w.task.insert("1.0", "Самоперевірка вікна Данте")
    w.show_help()
    pump(show_seconds)  # time to look at the window
    r.destroy()
    return res


def main() -> int:
    print("=== 1. Unit tests ===", flush=True)
    unit_ok = run_unit_tests()
    print("\n=== 2. Window checks ===", flush=True)
    try:
        res = run_window_checks(float(os.environ.get("DANTE_SELFTEST_SHOW", "10")))
    except Exception as e:  # report, do not hide
        import traceback
        traceback.print_exc()
        res = {f"window crashed: {e}": False}
    for name, ok in res.items():
        print(("  OK    " if ok else "  FAIL  ") + name)
    all_ok = unit_ok and all(res.values())
    print("\nRESULT:", "ALL PASSED" if all_ok else "PROBLEMS FOUND")
    return 0 if all_ok else 1
