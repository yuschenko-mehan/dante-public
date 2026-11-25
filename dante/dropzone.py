"""Drag files straight into a DANTE window (main window or the progress bar), like into a chat.
Windows: plain ctypes, no extra packages (WM_DROPFILES on the toplevel window). The dropped files are copied
to C:\\DANTE\\drop and a pult job is written; file_intake then reads/analyses them (reports in drop\\out).
Перетягування файлів прямо у вікно Данте (головне або смужку прогресу), як у чат.
Windows: лише ctypes, без додаткових пакетів. Файли копіюються в C:\\DANTE\\drop і пишеться завдання пульту."""
import json, os, shutil, sys, time
from pathlib import Path

DROP = Path(r"C:\DANTE\drop")
INBOX = Path(r"C:\DANTE\inbox")
JOB_CMD = r"cd /d C:\DANTE\dante & python C:\DANTE\proby\intake\drop_run.py"


def _get_free_name(drop_dir: Path, filename: str) -> str:
    """Find a unique file name in drop_dir, inserting ' (2)', ' (3)' before extension if needed.
    Знайти унікальне ім'я файлу в drop_dir, додаючи ' (2)', ' (3)' перед розширенням за потреби."""
    p = Path(filename)
    stem, suffix = p.stem, p.suffix
    candidate = filename
    counter = 2
    while (drop_dir / candidate).exists():
        candidate = f"{stem} ({counter}){suffix}"
        counter += 1
    return candidate


def handle_drop(paths, drop_dir=DROP, inbox=INBOX, now=time.time) -> dict:
    """Copy dropped files/folders into drop_dir without overwriting and write ONE pult job.
    Копіювати кинуті файли/теки в drop_dir без перезапису та записати одне завдання пульту."""
    drop_dir = Path(drop_dir)
    inbox = Path(inbox)
    
    copied = []
    skipped = []
    
    for raw_path in paths:
        p = Path(raw_path)
        if not p.exists():
            skipped.append(str(p))
            continue
            
        if p.is_file():
            drop_dir.mkdir(parents=True, exist_ok=True)
            free_name = _get_free_name(drop_dir, p.name)
            dest = drop_dir / free_name
            shutil.copy2(p, dest)
            copied.append(free_name)
        elif p.is_dir():
            drop_dir.mkdir(parents=True, exist_ok=True)
            folder_name = p.name
            # Recursively find all files inside the directory / Рекурсивно знайти всі файли всередині теки
            for sub_path in p.rglob("*"):
                if sub_path.is_file():
                    rel = sub_path.relative_to(p)
                    # Flatten with folder__sub__file name / Ущільнити з ім'ям folder__sub__file
                    flat_parts = [folder_name] + list(rel.parts)
                    flat_filename = "__".join(flat_parts)
                    free_name = _get_free_name(drop_dir, flat_filename)
                    dest = drop_dir / free_name
                    shutil.copy2(sub_path, dest)
                    copied.append(free_name)
        else:
            skipped.append(str(p))
            
    job_path = None
    if copied:
        inbox.mkdir(parents=True, exist_ok=True)
        ts_int = int(now() * 1000)
        job_file_name = f"zz-drop-{ts_int}.json"
        job_file_path = inbox / job_file_name
        
        job_data = {
            "kind": "cmd",
            "lane": "drop",
            "command": JOB_CMD,
            "timeout": 3600
        }
        job_file_path.write_text(json.dumps(job_data, ensure_ascii=False), encoding="utf-8")
        job_path = str(job_file_path)
        
    return {
        "copied": copied,
        "skipped": skipped,
        "job": job_path
    }


_KEEP = []          # keep ctypes callbacks alive / тримати колбеки живими


def hook_window(widget, callback) -> bool:
    """Accept files dropped from Explorer on the toplevel of a tkinter widget; callback(list_of_paths) runs in the
    Tk thread. Returns False if not on Windows or the hook failed. / Приймати файли з Провідника на вікно tkinter."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        user32, shell32 = ctypes.windll.user32, ctypes.windll.shell32
        WM_DROPFILES, WM_COPYDATA, WM_COPYGLOBALDATA, GWLP_WNDPROC = 0x0233, 0x004A, 0x0049, -4
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user32.GetParent.restype = wintypes.HWND
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        user32.CallWindowProcW.restype = LRESULT
        user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        shell32.DragQueryFileW.restype = wintypes.UINT
        shell32.DragQueryFileW.argtypes = [wintypes.WPARAM, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
        shell32.DragFinish.argtypes = [wintypes.WPARAM]
        shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
        widget.update_idletasks()
        hwnd = user32.GetParent(widget.winfo_id()) or widget.winfo_id()
        # let Explorer (normal rights) drop on an elevated window / дозволити кидання, якщо Данте запущено з правами адміна
        try:
            user32.ChangeWindowMessageFilterEx.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.DWORD, ctypes.c_void_p]
            for m in (WM_DROPFILES, WM_COPYDATA, WM_COPYGLOBALDATA):
                user32.ChangeWindowMessageFilterEx(hwnd, m, 1, None)
        except Exception:
            pass
        old = [None]

        def proc(h, msg, wp, lp):
            if msg == WM_DROPFILES:
                n = shell32.DragQueryFileW(wp, 0xFFFFFFFF, None, 0)
                files = []
                for i in range(n):
                    ln = shell32.DragQueryFileW(wp, i, None, 0) + 1
                    buf = ctypes.create_unicode_buffer(ln)
                    shell32.DragQueryFileW(wp, i, buf, ln)
                    files.append(buf.value)
                shell32.DragFinish(wp)
                widget.after(0, callback, files)
                return 0
            return user32.CallWindowProcW(old[0], h, msg, wp, lp)

        cb = WNDPROC(proc)
        _KEEP.append(cb)
        old[0] = user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(cb, ctypes.c_void_p))
        shell32.DragAcceptFiles(hwnd, True)
        return True
    except Exception:
        return False


def enable(widget, on_status=None) -> bool:
    """Hook a DANTE window: dropped files -> handle_drop; on_status(text) gets a short bilingual message.
    Під'єднати вікно Данте: кинуті файли -> handle_drop; on_status отримує коротке повідомлення."""
    def got(files):
        try:
            r = handle_drop(files)
            msg = (f"Прийнято файлів: {len(r['copied'])} — звіти будуть у C:\\DANTE\\drop\\out / "
                   f"{len(r['copied'])} file(s) taken, reports in drop\\out")
        except Exception as e:
            msg = f"Не вдалося прийняти файли / drop failed: {e}"
        if on_status:
            on_status(msg)
    return hook_window(widget, got)
