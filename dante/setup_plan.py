"""Setup wizard, part 1: look at this computer and make an install plan (nothing is installed here).

    python -m dante setup            — show the plan for this PC
The plan says: which components are missing (Python, Git, Node, Ollama, GPU driver), which local models
fit the hardware, which free cloud models are not connected yet (with the page where the author gets a key).
Installing follows the plan step by step, each step only with the author's consent; sign-ups, CAPTCHA, phone
codes and passwords are always done by the author; anything paid follows the money rule (two confirmations).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field


@dataclass
class Hardware:
    os: str = ""
    cpu_cores: int = 0
    ram_gb: float = 0.0
    free_disk_gb: float = 0.0
    gpus: list[dict] = field(default_factory=list)  # [{"name": "...", "vram_gb": 8.0}]

    @property
    def vram_gb(self) -> float:
        return max((g.get("vram_gb", 0.0) for g in self.gpus), default=0.0)

    @property
    def total_vram_gb(self) -> float:
        return sum(g.get("vram_gb", 0.0) for g in self.gpus)


# Local models: (ollama name, size on disk GB, needs VRAM GB to run fully on GPU, purpose)
LOCAL_MODELS = [
    ("qwen2.5-coder:3b", 2.0, 3.0, "код — швидка"),
    ("gemma3:4b", 3.3, 4.0, "зір — графіки, картинки"),
    ("qwen2.5-coder:7b", 4.7, 6.5, "код — сильніша"),
    ("qwen2.5vl:7b", 6.0, 7.5, "зір — графіки й схеми, сильніша"),
    ("qwen3:8b", 5.2, 7.0, "міркування, загальні задачі"),
    ("qwen2.5-coder:14b", 9.0, 12.0, "код — дуже сильна"),
]


def choose_local_models(hw: Hardware) -> list[dict]:
    """Pick local models that will work on this computer.

    Rule: a model is "gpu" if it fits into the biggest card (or into two cards together for >8 GB models),
    "mixed" if it fits into VRAM+RAM leaving 6 GB of RAM for Windows, otherwise skipped.
    Disk: keep at least 15 GB free after downloads.
    """
    out, disk_left = [], hw.free_disk_gb - 15
    ram_for_models = max(0.0, hw.ram_gb - 6)
    for name, disk, need, purpose in LOCAL_MODELS:
        if disk > disk_left:
            continue
        if need <= hw.vram_gb or (need > 8 and len(hw.gpus) > 1 and need <= hw.total_vram_gb):
            mode = "gpu"
        elif need <= hw.vram_gb + ram_for_models and need <= 8.5:
            mode = "mixed" if hw.gpus else "cpu"  # part on the card + RAM, or processor only — slower
        else:
            continue
        out.append({"model": name, "mode": mode, "disk_gb": disk, "purpose": purpose})
        disk_left -= disk
    return out


COMPONENTS = [  # (program, how to check, winget id, why)
    ("Python 3", "python", "Python.Python.3.13", "сам Данте"),
    ("Git", "git", "Git.Git", "точки відновлення, історія кроків"),
    ("Node.js", "node", "OpenJS.NodeJS.LTS", "агенти Gemini CLI / Codex"),
    ("Ollama", "ollama", "Ollama.Ollama", "локальні моделі без інтернету"),
]

FREE_PROVIDERS = [  # (key name in keys.txt, where the author gets a free key)
    ("GEMINI_API_KEY", "https://aistudio.google.com/apikey"),
    ("GROQ_API_KEY", "https://console.groq.com/keys"),
    ("OPENROUTER_API_KEY", "https://openrouter.ai/keys"),
    ("ZAI_API_KEY", "https://z.ai/manage-apikey/apikey-list"),
    ("MISTRAL_API_KEY", "https://console.mistral.ai/api-keys"),
    ("CEREBRAS_API_KEY", "https://cloud.cerebras.ai/"),
    ("CLOUDFLARE_API_TOKEN", "https://dash.cloudflare.com/profile/api-tokens"),
    ("COHERE_API_KEY", "https://dashboard.cohere.com/api-keys"),
    ("SAMBANOVA_API_KEY", "https://cloud.sambanova.ai/apis"),
    ("SARVAM_API_KEY", "https://dashboard.sarvam.ai/"),
    ("SILICONFLOW_API_KEY", "https://cloud.siliconflow.com/account/ak"),
    ("NVIDIA_API_KEY", "https://build.nvidia.com/settings/api-keys"),
]


def detect(run=subprocess.run) -> Hardware:
    """Read this computer's hardware. Works without admin rights; unknown values stay 0."""
    hw = Hardware(os=f"{platform.system()} {platform.release()} {platform.version()}",
                  cpu_cores=os.cpu_count() or 0)
    try:
        hw.free_disk_gb = round(shutil.disk_usage(os.path.abspath(os.sep)).free / 1e9, 1)
    except OSError:
        pass
    if os.name == "nt":
        ps = ("$m=(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory;"
              "$c=(Get-CimInstance Win32_Processor | Measure-Object NumberOfCores -Sum).Sum;"
              "@{ram=$m;cores=$c} | ConvertTo-Json")
        try:
            r = run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=30)
            d = json.loads(r.stdout or "{}")
            hw.ram_gb = round(float(d.get("ram") or 0) / 2**30, 1)
            hw.cpu_cores = int(d.get("cores") or hw.cpu_cores)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            with open("/proc/meminfo", encoding="utf-8") as f:
                kb = int(next(line for line in f if line.startswith("MemTotal")).split()[1])
            hw.ram_gb = round(kb / 2**20, 1)
        except (OSError, StopIteration, ValueError):
            pass
    hw.gpus = _nvidia_gpus(run)
    return hw


def _nvidia_gpus(run=subprocess.run) -> list[dict]:
    exe = shutil.which("nvidia-smi")
    if not exe and os.name == "nt":
        cand = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "NVIDIA Corporation", "NVSMI",
                            "nvidia-smi.exe")
        exe = cand if os.path.exists(cand) else None
    if not exe:
        return []
    try:
        r = run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    gpus = []
    for line in (r.stdout or "").splitlines():
        if "," in line:
            name, mem = line.rsplit(",", 1)
            try:
                gpus.append({"name": name.strip(), "vram_gb": round(float(mem) / 1024, 1)})
            except ValueError:
                pass
    return gpus


def make_plan(hw: Hardware, have_program=shutil.which, keys: dict | None = None,
              installed_models: set[str] | None = None) -> dict:
    keys = keys or {}
    installed_models = installed_models or set()
    missing = [{"component": n, "winget": w, "why": why} for n, cmd, w, why in COMPONENTS if not have_program(cmd)]
    models = choose_local_models(hw)
    for m in models:
        m["installed"] = m["model"] in installed_models
    providers = [{"key": k, "get_key_at": url} for k, url in FREE_PROVIDERS if not keys.get(k)]
    notes = []
    if not hw.gpus:
        notes.append("Відеокарту NVIDIA не знайдено: локальні моделі працюватимуть на процесорі (повільніше).")
    elif hw.vram_gb < 4:
        notes.append(f"Мала відеопам'ять ({hw.vram_gb} ГБ): великі моделі — частково в оперативній пам'яті.")
    if hw.ram_gb and hw.ram_gb < 8:
        notes.append("Менше 8 ГБ RAM: краще працювати переважно з хмарними безкоштовними моделями.")
    return {"hardware": asdict(hw), "missing_components": missing, "local_models": models,
            "free_providers_to_connect": providers, "notes": notes}


MODE_UK = {"gpu": "на відеокарті", "mixed": "відеокарта + RAM", "cpu": "лише процесор"}


def describe(plan: dict) -> str:
    hw = plan["hardware"]
    gpu = ", ".join(f"{g['name']} {g['vram_gb']} ГБ" for g in hw["gpus"]) or "немає NVIDIA"
    lines = [f"ПК: {hw['cpu_cores']} ядер, RAM {hw['ram_gb']} ГБ, вільно на диску {hw['free_disk_gb']} ГБ, "
             f"відеокарта: {gpu}", ""]
    lines.append("1) Програми, яких бракує:" if plan["missing_components"] else "1) Усі потрібні програми є.")
    lines += [f"   - {c['component']} ({c['why']}) — winget install {c['winget']}" for c in plan["missing_components"]]
    lines.append("2) Локальні моделі під це залізо:" if plan["local_models"]
                 else "2) Локальні моделі сюди не влазять — Данте працюватиме з хмарними безкоштовними.")
    lines += [f"   - {m['model']}: {m['purpose']} ({MODE_UK[m['mode']]}, "
              f"{m['disk_gb']} ГБ){' — вже є' if m['installed'] else ''}" for m in plan["local_models"]]
    lines.append("3) Безкоштовні хмарні моделі, ще не підключені (ключ отримуєте ви, Данте збереже):"
                 if plan["free_providers_to_connect"] else "3) Усі безкоштовні хмарні входи підключені.")
    lines += [f"   - {p['key']}: {p['get_key_at']}" for p in plan["free_providers_to_connect"]]
    lines += [""] + plan["notes"] if plan["notes"] else []
    return "\n".join(lines)


def main() -> int:
    from dante.config import _file_keys
    installed = set()
    if shutil.which("ollama"):
        try:
            r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=20)
            installed = {ln.split()[0] for ln in (r.stdout or "").splitlines()[1:] if ln.strip()}
        except (OSError, subprocess.TimeoutExpired):
            pass
    print(describe(make_plan(detect(), keys=_file_keys(), installed_models=installed)))
    return 0
