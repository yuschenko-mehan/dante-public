"""DANTE file intake: take ANY file, read it and optionally analyse it with a model (Claude reference, 25.11.2026).
Прийом файлів Данте: будь-який файл — прочитати й за бажанням проаналізувати моделлю (еталон Claude)."""
import csv, hashlib, io, json, re, shutil, struct, subprocess, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

EXT = {
    "text": {".txt", ".md", ".log", ".ini", ".cfg", ".toml", ".yaml", ".yml", ".xml", ".html", ".htm", ".rtf", ".srt"},
    "code": {".py", ".rs", ".js", ".ts", ".c", ".h", ".cpp", ".hpp", ".cs", ".java", ".go", ".ino", ".bat", ".cmd",
             ".ps1", ".sh", ".sql", ".css", ".kt", ".php", ".rb", ".lua"},
    "csv": {".csv", ".tsv"}, "json": {".json", ".jsonl"}, "pdf": {".pdf"}, "docx": {".docx"}, "xlsx": {".xlsx"},
    "pptx": {".pptx"}, "image": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}, "dxf": {".dxf"},
    "zip": {".zip"}, "audio": {".mp3", ".wav", ".ogg", ".flac", ".m4a"}, "video": {".mp4", ".avi", ".mkv", ".mov", ".webm"},
}
IMAGE_Q = "Опиши, що на зображенні; якщо є текст або код — перепиши його точно."


def detect(path) -> str:
    """Kind by extension, then by magic bytes / Тип за розширенням, потім за першими байтами."""
    p = Path(path)
    ext = p.suffix.lower()
    for kind, exts in EXT.items():
        if ext in exts:
            return kind
    head = p.read_bytes()[:16]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8\xff") or head.startswith(b"GIF8"):
        return "image"
    if head.startswith(b"PK\x03\x04"):
        return "zip"
    block = p.read_bytes()[:4096]
    if b"\x00" in block:                        # NUL bytes: not text / нульові байти — не текст
        return "binary"
    try:
        block.decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        return "binary"


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _docx(z):
    root = ET.fromstring(z.read("word/document.xml"))
    paras = []
    for p in root.iter():
        if _local(p.tag) == "p":
            paras.append("".join(t.text or "" for t in p.iter() if _local(t.tag) == "t"))
    return "\n".join(paras), {"paragraphs": len(paras)}


def _xlsx(z):
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
            shared.append("".join(t.text or "" for t in si.iter() if _local(t.tag) == "t"))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {}
    if "xl/_rels/workbook.xml.rels" in z.namelist():
        for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")):
            rels[r.get("Id")] = r.get("Target", "")
    sheets, out = [], []
    for i, s in enumerate(e for e in wb.iter() if _local(e.tag) == "sheet"):
        name = s.get("name")
        sheets.append(name)
        rid = next((v for k, v in s.attrib.items() if _local(k) == "id"), None)
        target = rels.get(rid, f"worksheets/sheet{i + 1}.xml").lstrip("/")
        target = target if target.startswith("xl/") else "xl/" + target
        out.append(f"--- sheet {name} ---")
        if target not in z.namelist():
            continue
        for row in (e for e in ET.fromstring(z.read(target)).iter() if _local(e.tag) == "row"):
            cells = []
            for c in (e for e in row if _local(e.tag) == "c"):
                t = c.get("t")
                v = next((e.text for e in c if _local(e.tag) == "v"), None)
                if t == "s" and v is not None:
                    cells.append(shared[int(v)])
                elif t == "inlineStr":
                    cells.append("".join(x.text or "" for x in c.iter() if _local(x.tag) == "t"))
                else:
                    cells.append(v or "")
            out.append("\t".join(cells))
    return "\n".join(out), {"sheets": sheets}


def _pptx(z):
    slides = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                    key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
    out = []
    for n in slides:
        k = int(re.search(r"(\d+)\.xml$", n).group(1))
        root = ET.fromstring(z.read(n))
        out.append(f"--- slide {k} ---")
        out.append("\n".join(t.text or "" for t in root.iter() if _local(t.tag) == "t"))
    return "\n".join(out), {"slides": len(slides)}


def _image_size(data: bytes):
    if data.startswith(b"\x89PNG") and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24]); return w, h
    if data.startswith(b"GIF8") and len(data) >= 10:
        w, h = struct.unpack("<HH", data[6:10]); return w, h
    if data.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1; continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9]); return w, h
            seg = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg
    return None, None


def _dxf(text: str):
    lines = [l.strip() for l in text.splitlines()]
    pairs = list(zip(lines[0::2], lines[1::2]))
    ents, texts, in_ent, cur = {}, [], False, None
    for code, val in pairs:
        if code == "2" and val == "ENTITIES":
            in_ent = True; continue
        if code == "0":
            if val == "ENDSEC":
                in_ent = False; cur = None; continue
            if in_ent:
                cur = val; ents[val] = ents.get(val, 0) + 1
            continue
        if in_ent and cur in ("TEXT", "MTEXT") and code in ("1", "3"):
            texts.append(val)
    return "\n".join(texts), {"entities": ents}


def _ffprobe(path):
    if not shutil.which("ffprobe"):
        return {}
    try:
        r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
                           capture_output=True, timeout=30)
        f = json.loads(r.stdout or b"{}").get("format", {})
        return {k: f[k] for k in ("duration", "format_name", "bit_rate") if k in f}
    except Exception:
        return {}


def read_any(path, vision=None, max_chars: int = 200000) -> dict:
    """Read any file into {kind, name, size, sha256, text, meta, error}; never raises for a readable path.
    Прочитати будь-який файл; помилки — у полі error, а не винятком."""
    p = Path(path)
    data = p.read_bytes()
    kind = detect(p)
    res = {"kind": kind, "name": p.name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
           "text": "", "meta": {}, "error": None}
    try:
        if kind in ("text", "code"):
            res["text"] = _decode(data)
            res["meta"]["lines"] = len(res["text"].splitlines())
        elif kind == "csv":
            res["text"] = _decode(data)
            rows = list(csv.reader(io.StringIO(res["text"]), delimiter="\t" if p.suffix.lower() == ".tsv" else ","))
            rows = [r for r in rows if r]
            res["meta"]["columns"] = rows[0] if rows else []
            res["meta"]["rows"] = max(0, len(rows) - 1)
        elif kind == "json":
            res["text"] = _decode(data)
            try:
                obj = json.loads(res["text"])
                if isinstance(obj, dict):
                    res["meta"]["keys"] = sorted(obj)
            except ValueError as e:
                res["error"] = f"json: {e}"
        elif kind in ("docx", "xlsx", "pptx"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                res["text"], m = {"docx": _docx, "xlsx": _xlsx, "pptx": _pptx}[kind](z)
            res["meta"].update(m)
        elif kind == "pdf":
            try:
                import pypdf
            except ImportError:
                res["error"] = "pypdf is not installed (pip install pypdf) / не встановлено pypdf"
            else:
                rd = pypdf.PdfReader(io.BytesIO(data))
                res["meta"]["pages"] = len(rd.pages)
                res["text"] = "\n".join(f"--- page {i + 1} ---\n" + (pg.extract_text() or "") for i, pg in enumerate(rd.pages))
        elif kind == "image":
            w, h = _image_size(data)
            if w:
                res["meta"]["width"], res["meta"]["height"] = w, h
            if vision:
                res["text"] = vision(str(p), IMAGE_Q) or ""
        elif kind == "dxf":
            res["text"], m = _dxf(_decode(data)); res["meta"].update(m)
        elif kind == "zip":
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = [n for n in z.namelist() if not n.endswith("/")]
            res["meta"]["files"] = names
            res["text"] = "\n".join(names)
        elif kind in ("audio", "video"):
            res["meta"].update(_ffprobe(p))
        else:
            res["meta"]["magic"] = data[:16].hex()
    except Exception as e:                       # broken file: report, never crash / зламаний файл — звіт
        res["error"] = f"{type(e).__name__}: {e}"
    if len(res["text"]) > max_chars:
        res["text"] = res["text"][:max_chars]
        res["meta"]["truncated"] = True
    return res


SYSTEM = ("Ти аналітик файлів Данте. Коротко українською: що це за файл, головний зміст, важливі числа/дати/імена, "
          "помилки чи ризики, що з ним можна зробити далі. Не вигадуй того, чого немає в тексті.")


def analyze(path, llm=None, vision=None, question=None) -> dict:
    """read_any + a model's answer / Прочитати і отримати відповідь моделі."""
    info = read_any(path, vision=vision)
    info["answer"] = ""
    if llm is not None:
        user = (f"Файл: {info['name']}\nТип: {info['kind']}\nРозмір: {info['size']} байт\n"
                f"Дані: {json.dumps(info['meta'], ensure_ascii=False)[:2000]}\n"
                + (f"Питання: {question}\n" if question else "")
                + f"Вміст (початок):\n{info['text'][:12000]}")
        try:
            info["answer"] = llm.complete(SYSTEM, user).content
        except Exception as e:
            info["error"] = (info["error"] or "") + f" | llm: {e}"
    return info


def process_drop(drop_dir, out_dir, llm=None, vision=None) -> list:
    """Every file in drop_dir -> report out_dir/<name>.md, original -> drop_dir/done/.
    Кожен файл з теки -> звіт <ім'я>.md, оригінал -> done/."""
    drop, out = Path(drop_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    done = drop / "done"
    reports = []
    for f in sorted(x for x in drop.iterdir() if x.is_file()):
        info = analyze(f, llm=llm, vision=vision)
        rep = out / (f.name + ".md")
        rep.write_text(
            f"# {info['name']}\n\n- Тип / kind: {info['kind']}\n- Розмір / size: {info['size']} B\n"
            f"- SHA-256: {info['sha256']}\n- Дані / meta: {json.dumps(info['meta'], ensure_ascii=False)[:3000]}\n"
            + (f"- Помилка / error: {info['error']}\n" if info["error"] else "")
            + f"\n## Аналіз / Analysis\n\n{info['answer'] or '(без моделі / no model)'}\n\n"
            f"## Вміст (початок) / Content (head)\n\n```\n{info['text'][:4000]}\n```\n", encoding="utf-8")
        done.mkdir(exist_ok=True)
        target = done / f.name
        if target.exists():
            target.unlink()
        shutil.move(str(f), str(target))
        reports.append(str(rep))
    return reports
