import json, subprocess
from dataclasses import dataclass, field

@dataclass
class Summary:
    maker: str = ""; model: str = ""; board_vendor: str = "other"; board: str = ""; bios: str = ""
    cpu: str = ""; cores: int = 0; threads: int = 0; ram_gb: int = 0; gpu: str = ""; vram_gb: int = 0; free_disk_gb: int = 0

@dataclass
class Forecast:
    local_models: list = field(default_factory=list); parallel_jobs: int = 2; notes: list = field(default_factory=list)

@dataclass
class Guide:
    keys: str; steps: list; caution: str

_V = (("micro-star", "msi"), ("msi", "msi"), ("gigabyte", "gigabyte"), ("asrock", "asrock"), ("asus", "asus"), ("dell", "dell"),
      ("hewlett", "hp"), ("hp", "hp"), ("lenovo", "lenovo"), ("acer", "acer"))

def vendor_of(s):
    s = (s or "").lower()
    for k, v in _V:
        if s.startswith(k) or k in s.split() or (len(k) > 3 and k in s):
            return v
    return "other"

def summarize(raw):
    sy, b, bi, c = raw.get("system", {}), raw.get("board", {}), raw.get("bios", {}), raw.get("cpu", {})
    g = (raw.get("gpus") or [{}])[0]
    vram = raw.get("vram_mb_nvidia") or (g.get("AdapterRAM") or 0) // 1024 ** 2
    free = sum(d.get("FreeSpace") or 0 for d in raw.get("disks", []) if d.get("DeviceID", "").upper() == "C:")
    return Summary(sy.get("Manufacturer", ""), sy.get("Model", ""), vendor_of(b.get("Manufacturer") or sy.get("Manufacturer")),
                   b.get("Product", ""), f"{bi.get('Manufacturer', '')} {bi.get('SMBIOSBIOSVersion', '')}".strip(), c.get("Name", ""),
                   int(c.get("NumberOfCores") or 0), int(c.get("NumberOfLogicalProcessors") or 0),
                   round((raw.get("ram_bytes") or 0) / 1024 ** 3), g.get("Name", ""), round(vram / 1024), round(free / 1024 ** 3))

_MODELS = (("qwen2.5-coder:3b", 4), ("gemma3:4b", 6), ("qwen2.5vl:3b", 6), ("qwen2.5-coder:7b", 10), ("qwen2.5-coder:14b", 20), ("qwen2.5-coder:32b", 40))

def forecast(s):
    mem = s.ram_gb + s.vram_gb
    f = Forecast([m for m, need in _MODELS if mem >= need and s.ram_gb >= need * 0.6], max(2, s.threads // 4))
    if s.vram_gb < 4:
        f.notes.append("Мало відеопам'яті: локальні моделі працюють частково на процесорі, повільніше.")
    if mem < 8:
        f.notes.append("Мало пам'яті: краще хмарні безкоштовні моделі.")
    if not f.notes:
        f.notes.append("Ресурсів достатньо для локальних моделей.")
    return f

_G = {"asus": ("Del або F2", ["Advanced", "APM Configuration", "Restore AC Power Loss → Power On"]),
      "msi": ("Del", ["Settings", "Advanced → Power Management Setup", "Restore after AC Power Loss → Power On"]),
      "gigabyte": ("Del", ["Settings", "Platform Power", "AC BACK → Always On (Power On)"]),
      "asrock": ("F2 або Del", ["Advanced", "Chipset Configuration", "Restore on AC/Power Loss → Power On"]),
      "dell": ("F2", ["Power Management", "AC Recovery", "Power On"]),
      "hp": ("F10", ["Advanced", "Power-On Options", "After Power Loss → On (Power On)"]),
      "lenovo": ("F1 або F2", ["Power", "After Power Loss", "Power On"]),
      "acer": ("Del або F2", ["Advanced / Power", "Restore on AC Power Loss", "Power On"]),
      "other": ("Del, F2, F10 або F1", ["Розділ Power / Advanced", "Пункт AC Power Loss / AC Recovery / After Power Loss", "Значення Power On"])}

def bios_power_guide(vendor, lang="uk"):
    k, st = _G.get(vendor, _G["other"])
    steps = [f"Увімкніть ПК і одразу натискайте {k}" if lang == "uk" else f"Turn on the PC and press {k} right away"] + st + \
            (["F10 — зберегти й вийти"] if lang == "uk" else ["F10 — save and exit"])
    if lang != "uk":
        k = k.replace("або", "or"); steps = [s.replace("Розділ", "Section").replace("Пункт", "Item").replace("Значення", "Value") for s in steps]
    caution = ("Назви пунктів залежать від версії BIOS; якщо не знайшли — шукайте слова «AC Power» або «Power Loss»." if lang == "uk"
               else "Menu names depend on the BIOS version; if not found, look for \"AC Power\" or \"Power Loss\".")
    return Guide(k, steps, caution)

def report(s, lang="uk"):
    f, g = forecast(s), bios_power_guide(s.board_vendor, lang)
    return "\n".join([f"ПК: {s.maker} {s.model}", f"Плата: {s.board} · BIOS {s.bios}", f"Процесор: {s.cpu} ({s.cores}/{s.threads})",
                      f"Пам'ять: {s.ram_gb} ГБ · Відеокарта: {s.gpu} ({s.vram_gb} ГБ)", f"Вільно на C: {s.free_disk_gb} ГБ",
                      f"Локальні моделі: {', '.join(f.local_models) or '—'} · завдань одночасно: {f.parallel_jobs}", *f.notes,
                      f"BIOS, увімкнення після світла ({g.keys}):", *[f"  {i}. {x}" for i, x in enumerate(g.steps, 1)], g.caution])

def collect_command():
    ps = ("$o=@{system=(Get-CimInstance Win32_ComputerSystem|select Manufacturer,Model);board=(Get-CimInstance Win32_BaseBoard|select Manufacturer,Product);"
          "bios=(Get-CimInstance Win32_BIOS|select Manufacturer,SMBIOSBIOSVersion);cpu=(Get-CimInstance Win32_Processor|select -First 1 Name,NumberOfCores,NumberOfLogicalProcessors);"
          "ram_bytes=(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory;gpus=@(Get-CimInstance Win32_VideoController|select Name,AdapterRAM);"
          "disks=@(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3'|select DeviceID,FreeSpace,Size)};"
          "try{$o.vram_mb_nvidia=[int]((nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits)|select -First 1)}catch{};$o|ConvertTo-Json -Depth 4")
    return ["powershell", "-NoProfile", "-Command", ps]

def collect(run=None):
    run = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout)
    return json.loads(run(collect_command()))


if __name__ == "__main__":
    import sys
    raw = collect()
    if "--raw" in sys.argv:
        print(json.dumps(raw, ensure_ascii=False, indent=1)[:3000])
    print(report(summarize(raw), "uk"))
