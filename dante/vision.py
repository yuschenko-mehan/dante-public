"""Vision module for interacting with local Ollama vision models.
Модуль зору для взаємодії з локальними моделями зору Ollama."""

import base64
import json
import urllib.request
import urllib.error
from pathlib import Path

# Default model used for vision tasks / Модель за замовчуванням для завдань зору
DEFAULT_MODEL = 'gemma3:4b'

# Maximum allowed image size in bytes (8 MB) / Максимальний дозволений розмір зображення в байтах (8 МБ)
MAX_BYTES = 8 * 1024 * 1024


def _default_post(url, payload, timeout):
    """Default JSON POST request implementation using standard library.
    Реалізація JSON POST запиту за замовчуванням з використанням стандартної бібліотеки."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _validate_and_read_image(image_path):
    """Validate image existence, size, and magic bytes, then return base64 encoded string.
    Перевірити наявність, розмір та магічні байти зображення, потім повернути рядок у кодуванні base64."""
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Image file not found: {path}")

    # Check file size / Перевірити розмір файлу
    file_size = path.stat().st_size
    if file_size > MAX_BYTES:
        raise ValueError(f"Image file too large: {file_size} bytes (max {MAX_BYTES})")

    # Read first bytes for magic number check / Прочитати перші байти для перевірки магічного числа
    header = path.read_bytes()
    if not header:
        raise ValueError("Image file is empty")

    # Check magic bytes for PNG, JPEG, GIF, BMP, WEBP
    # Перевірити магічні байти для PNG, JPEG, GIF, BMP, WEBP
    is_png = header.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpeg = header.startswith(b"\xff\xd8\xff")
    is_gif = header.startswith(b"GIF87a") or header.startswith(b"GIF89a")
    is_bmp = header.startswith(b"BM")
    is_webp = header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WEBP"

    if not (is_png or is_jpeg or is_gif or is_bmp or is_webp):
        raise ValueError("Not a valid PNG, JPEG, GIF, BMP, or WEBP image")

    return base64.b64encode(header).decode("utf-8")


def look(image, question, model=DEFAULT_MODEL, host='http://127.0.0.1:11434', post=_default_post, timeout=300):
    """Send an Ollama /api/chat request with an image and question.
    Надіслати запит до Ollama /api/chat із зображенням та запитанням."""
    b64_image = _validate_and_read_image(image)

    url = f"{host.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": question,
                "images": [b64_image]
            }
        ]
    }

    result = post(url, payload, timeout)

    # Extract answer text from response / Витягти текст відповіді з результату
    if isinstance(result, dict):
        message = result.get("message", {})
        answer = message.get("content", "")
    else:
        answer = ""

    if not answer or not str(answer).strip():
        raise RuntimeError("Received empty answer from model")

    return answer


def main(argv=None, post=_default_post, say=print):
    """CLI entry point for vision commands.
    Точка входу командного рядка для команд зору."""
    import sys
    if argv is None:
        argv = sys.argv[1:]

    image_path = None
    question = None
    model = DEFAULT_MODEL

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--ask":
            if i + 1 < len(argv):
                question = argv[i + 1]
                i += 2
                continue
        elif arg == "--model":
            if i + 1 < len(argv):
                model = argv[i + 1]
                i += 2
                continue
        elif image_path is None:
            image_path = arg
        i += 1

    if not image_path or not question:
        raise ValueError("Usage: image --ask TEXT [--model NAME]")

    answer = look(image_path, question, model=model, post=post)
    say(answer)
    return 0
