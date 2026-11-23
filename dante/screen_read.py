"""Screen reader (Vision 2 for the Writer). Captures screens or windows, asks local vision models, and parses code files.
Зчитувач екрана (Зір 2 для Писаря). Знімає екрани або вікна, запитує локальні моделі зору та аналізує файли коду."""

import argparse
import datetime
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

from dante import answer_files, vision

MODES: Tuple[str, str, str] = ("code", "text", "physics")

@dataclass
class ScreenResult:
    # Screen result container / Контейнер результату зняття екрана
    mode: str
    image: Path
    text: str
    files: Dict[str, str] = field(default_factory=dict)


def prompt(mode: str, extra: str = "") -> str:
    # Build prompt based on mode / Створити промпт на основі режиму
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode} / Невідомий режим: {mode}")
    
    base = ""
    if mode == "code":
        base = (
            "Read the code EXACTLY keeping indentation, each file as file name line, language line, code."
        )
    elif mode == "text":
        base = "Transcribe all readable text exactly."
    elif mode == "physics":
        base = (
            "Describe real objects — what they are, material, approximate size, forces, motion, safety risks."
        )
    
    if extra:
        return f"{base}\n\n{extra}"
    return base


def save_files(folder: Union[str, Path], files: Dict[str, str]) -> List[str]:
    # Save parsed files securely inside folder / Безпечно зберегти розібрані файли всередині папки
    folder_path = Path(folder).resolve()
    saved: List[str] = []
    
    for filename, content in files.items():
        if ".." in filename or filename.startswith("/") or ":" in filename or "\\" in filename:
            # Reject unsafe paths / Відхилити небезпечні шляхи
            # But let's check relative path components
            pass
        
        try:
            # Build target path and verify it stays inside folder_path
            # Побудувати цільовий шлях та переконатися, що він залишається всередині folder_path
            target = (folder_path / filename).resolve()
            if not target.is_relative_to(folder_path):
                continue
            
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            saved.append(filename)
        except Exception:
            # Skip invalid paths / Пропустити недійсні шляхи
            continue
            
    return saved


def capture_command(out_path: Union[str, Path], window: Optional[str] = None) -> List[str]:
    # Generate PowerShell command list for screen capture / Згенерувати список команд PowerShell для захоплення екрана
    out_str = str(Path(out_path))
    
    if window:
        ps_script = f"""
Add-Type -AssemblyName System.Drawing
$hwnd = (Get-Process | Where-Object {{$_.MainWindowTitle -like '*{window}*'}} | Select-Object -First 1).MainWindowHandle
if ($hwnd) {{
    Add-Type @'
    using System;
    using System.Runtime.InteropServices;
    public class Win32 {{
        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
        [StructLayout(LayoutKind.Sequential)]
        public struct RECT {{ public int Left; public int Top; public int Right; public int Bottom; }}
    }}
'@
    $rect = New-Object Win32+RECT
    [Win32]::GetWindowRect($hwnd, [ref]$rect)
    $w = $rect.Right - $rect.Left
    $h = $rect.Bottom - $rect.Top
    if ($w -gt 0 -and $h -gt 0) {{
        $bmp = New-Object System.Drawing.Bitmap $w, $h
        $graphics = [System.Drawing.Graphics]::FromImage($bmp)
        $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, (New-Object System.Drawing.Size($w, $h)))
        $bmp.Save('{out_str}')
        $graphics.Dispose()
        $bmp.Dispose()
        exit 0
    }}
}}
# Fallback to primary screen
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bmp.Save('{out_str}')
$graphics.Dispose()
$bmp.Dispose()
"""
    else:
        ps_script = f"""
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bmp.Save('{out_str}')
$graphics.Dispose()
$bmp.Dispose()
"""

    return ["powershell", "-Command", ps_script]


def default_capture(out_path: Union[str, Path], window: Optional[str] = None) -> Path:
    # Execute capture command / Виконати команду захоплення
    cmd = capture_command(out_path, window=window)
    subprocess.run(cmd, check=True)
    return Path(out_path)


def read_screen(
    mode: str,
    out_dir: Union[str, Path],
    window: Optional[str] = None,
    image: Optional[Union[str, Path]] = None,
    extra: str = "",
    capture: Callable = default_capture,
    look: Callable = vision.look,
    model: Optional[str] = None,
    now: str = "",
) -> ScreenResult:
    # Read screen or window using vision model / Прочитати екран або вікно за допомогою моделі зору
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode}")
        
    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)
    
    if not now:
        now = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        
    img_path = Path(image) if image else out_dir_path / f"screen-{now}.png"
    
    if not image:
        capture(img_path, window=window)
        
    q = prompt(mode, extra)
    text = look(img_path, q, model=model)
    
    files: Dict[str, str] = {}
    if mode == "code":
        files = answer_files.parse(text)
        if files:
            save_files(out_dir_path, files)
            
    return ScreenResult(mode=mode, image=img_path, text=text, files=files)


def main(argv: Optional[List[str]] = None, say: Callable = print) -> int:
    # CLI entry point for screen reader / Точка входу CLI для зчитувача екрана
    parser = argparse.ArgumentParser(description="Dante Screen Reader / Зчитувач екрана Данте")
    parser.add_argument("mode", choices=MODES, help="Mode: code, text, physics")
    parser.add_argument("--window", help="Window title substring")
    parser.add_argument("--image", help="Existing image path")
    parser.add_argument("--ask", default="", help="Extra question")
    parser.add_argument("--out", default=".", help="Output directory")
    
    args = parser.parse_args(argv)
    
    res = read_screen(
        mode=args.mode,
        out_dir=args.out,
        window=args.window,
        image=args.image,
        extra=args.ask,
    )
    
    say(res.text)
    if res.files:
        say("Saved files / Збережені файли: " + ", ".join(res.files.keys()))
        
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
