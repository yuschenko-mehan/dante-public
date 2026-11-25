"""Process C:\\DANTE\\drop with DANTE's free models (team a) and DANTE's eye; reports -> C:\\DANTE\\drop\\out.
Обробити теку C:\\DANTE\\drop безкоштовними моделями Данте (команда a) і зором; звіти -> C:\\DANTE\\drop\\out."""
import sys
from pathlib import Path
sys.path[:0] = [r"C:\DANTE\proby\intake", r"C:\DANTE\dante"]
import file_intake as FI
from dante.config import load_settings
from dante.llm import build_llm
from dante import vision

DROP = Path(r"C:\DANTE\drop")
DROP.mkdir(parents=True, exist_ok=True)
llm = build_llm(load_settings(Path(r"C:\DANTE\dante\team-a.toml")))
reps = FI.process_drop(DROP, DROP / "out", llm=llm, vision=vision.look)
print("reports / звіти:", *reps, sep="\n  ")
