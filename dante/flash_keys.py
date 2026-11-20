"""DANTE keys to/from a USB flash drive, encrypted with your passphrase (AES-256-GCM, key from scrypt).
Ключі Данте на флешку і з флешки, зашифровані вашою фразою (AES-256-GCM, ключ через scrypt).
The passphrase is typed only here, on this PC; it is never saved anywhere.
Фраза вводиться лише тут, на цьому ПК, і ніде не зберігається."""
import ctypes, getpass, io, json, os, string, subprocess, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]   # the DANTE folder / папка Данте
FILES = [ROOT / "keys.txt", ROOT / "models.json"]
NAME = "DANTE-keys.flash"
MAGIC = b"DANTE-FLASH-PY-1\n"


def need_crypto():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
    except ImportError:
        print("Встановлюю модуль шифрування (один раз)...")
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "cryptography"], check=True)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM


def usb_drives():
    out = []
    for L in string.ascii_uppercase:
        root = f"{L}:\\"
        if os.path.exists(root) and ctypes.windll.kernel32.GetDriveTypeW(root) == 2:
            out.append(root)
    return out


def key_from(phrase, salt):
    import hashlib
    return hashlib.scrypt(phrase.encode("utf-8"), salt=salt, n=2 ** 15, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)


def pick_drive():
    d = usb_drives()
    if not d:
        print("Флешку не знайдено. Вставте флешку і запустіть ще раз.")
        return None
    if len(d) == 1:
        return d[0]
    print("Знайдено флешки:", ", ".join(d))
    a = input("Буква флешки (наприклад E): ").strip().upper()[:1]
    return f"{a}:\\" if f"{a}:\\" in d else None


def to_flash():
    AESGCM = need_crypto()
    drive = pick_drive()
    if not drive:
        return 1
    while True:
        p1 = input("Придумайте фразу-пароль (не менше 10 знаків) і натисніть Enter: ").strip()
        if len(p1) < 10:
            print("Закоротка (зараз", len(p1), "знаків). Ще раз."); continue
        print("Ваша фраза:", p1)
        if input("Усе правильно? Введіть так або ні: ").strip().lower() not in ("так", "т", "yes", "y", "lfr"):
            continue
        break
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in FILES:
            if f.exists():
                z.write(f, f.name)
    salt, nonce = os.urandom(16), os.urandom(12)
    head = json.dumps({"kdf": "scrypt", "n": 2 ** 15, "r": 8, "p": 1, "salt": salt.hex(), "nonce": nonce.hex()}).encode()
    blob = AESGCM(key_from(p1, salt)).encrypt(nonce, buf.getvalue(), MAGIC + head)
    target = Path(drive) / NAME
    target.write_bytes(MAGIC + head + b"\n" + blob)
    import shutil
    shutil.copy2(__file__, Path(drive) / "flash_keys.py")   # a copy for a PC without DANTE / копія на всяк випадок
    print(f"ГОТОВО: {target}  (вдома: кнопка «Ключі ← флешка» у Данте)")
    print("Файли:", ", ".join(f.name for f in FILES if f.exists()))
    return 0


def from_flash():
    AESGCM = need_crypto()
    drive = pick_drive()
    if not drive:
        return 1
    data = (Path(drive) / NAME).read_bytes()
    if not data.startswith(MAGIC):
        print("Це не файл ключів Данте."); return 1
    head, blob = data[len(MAGIC):].split(b"\n", 1)
    h = json.loads(head)
    phrase = input("Фраза-пароль флешки і Enter: ").strip()
    try:
        raw = AESGCM(key_from(phrase, bytes.fromhex(h["salt"]))).decrypt(bytes.fromhex(h["nonce"]), blob, MAGIC + head)
    except Exception:
        print("Фраза неправильна (або файл пошкоджено)."); return 1
    dest = ROOT
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for n in z.namelist():
            p = dest / Path(n).name
            if p.exists():
                p.replace(p.with_suffix(p.suffix + ".before-flash"))
            p.write_bytes(z.read(n))
            print("відновлено:", p)
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "to"
    rc = to_flash() if mode == "to" else from_flash()
    input("\nНатисніть Enter, щоб закрити.")
    sys.exit(rc)
