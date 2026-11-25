"""Site-independent ask/answer for web AI chats (Claude, 24.11.2026).
The prompt ends with a unique token; the answer is the page text AFTER the last copy of that token, so DANTE does
not need to know how each site marks its messages. The send button is searched by a priority list, close to the
input box. Питання/відповідь для будь-якого веб-чату: запит закінчується унікальною міткою, відповідь — текст
сторінки ПІСЛЯ останньої мітки; кнопку надсилання шукаємо за списком пріоритетів біля поля вводу."""
from __future__ import annotations

import json
import random
import time

SEND_PRIORITY = (
    'button[data-testid="send-button"]', 'button.send-button', 'button[aria-label="Надіслати повідомлення"]',
    'button[aria-label*="Send message" i]', 'button[aria-label*="Надіслати"]', 'button[aria-label*="Send" i]',
    '.ds-button--primary.ds-button--filled', 'div[class*="send-button"]', 'button[type="submit"]',
)
BODY_JS = "document.body ? document.body.innerText : ''"
# Chats render answers as Markdown: indentation and __names__ get lost in the page text, but a code block keeps
# the text exactly. So we ask for ONE code block and read code blocks (<pre>) that come after the token.
# Чати показують відповідь як Markdown: відступи й __імена__ губляться, а блок коду зберігає текст точно.
CODE_BLOCK_RULE = ("Put ALL the files together inside ONE single code block (```text at the start, ``` at the end), "
                   "with the === FILE === / === END FILE === markers inside that block.")


PRE_COUNT_JS = "document.querySelectorAll('pre').length"


def pre_after_token_js(token: str, n0: int = 0) -> str:
    """JS: text of all <pre> blocks after the last copy of the token; if the site does not show the token (DeepSeek),
    the <pre> blocks that appeared after sending (index >= n0). / Блоки <pre> після мітки або нові після надсилання."""
    js = r"""(() => {
  const tok = __TOK__, n0 = __N0__;
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n, last = null;
  while ((n = w.nextNode())) if (n.textContent.includes(tok)) last = n;
  const all = Array.from(document.querySelectorAll('pre'));
  if (!last) return all.slice(n0).map(p => p.textContent).join('\n');
  return all.filter(p => last.compareDocumentPosition(p) & Node.DOCUMENT_POSITION_FOLLOWING)
    .map(p => p.textContent).join('\n');
})()"""
    return js.replace("__TOK__", json.dumps(token)).replace("__N0__", str(int(n0)))


def send_js(text: str) -> str:
    """JS: type `text` into the chat box and press the best send button near it (Enter if none).
    JS: ввести текст у поле чату й натиснути найкращу кнопку надсилання поруч (або Enter)."""
    return r"""(() => {
  const text = %s, PRI = %s;
  const vis = e => e && e.offsetParent !== null;
  const pref = Array.from(document.querySelectorAll('.ql-editor[contenteditable="true"], #prompt-textarea, textarea#chat-input, textarea.message-input-textarea')).filter(vis);
  const boxes = pref.length ? pref : Array.from(document.querySelectorAll('textarea, [contenteditable="true"]')).filter(vis);
  const box = boxes[boxes.length - 1];
  if (!box) return 'no-box';
  box.focus();
  if (box.tagName === 'TEXTAREA') {
    const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
    set.call(box, text); box.dispatchEvent(new Event('input', {bubbles: true}));
  } else { document.execCommand('selectAll', false, null); document.execCommand('insertText', false, text); }
  setTimeout(() => {
    let area = box; for (let k = 0; k < 8 && area.parentElement; k++) area = area.parentElement;
    for (const s of PRI) {
      const b = Array.from(area.querySelectorAll(s)).find(e => vis(e) && !e.disabled && e.getAttribute('aria-disabled') !== 'true');
      if (b) {                                   // full pointer sequence: some sites ignore a bare click()
        for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup'])
          b.dispatchEvent(new MouseEvent(t, {bubbles: true, cancelable: true, view: window}));
        b.click(); return;
      }
    }
    for (const t of ['keydown', 'keypress', 'keyup'])
      box.dispatchEvent(new KeyboardEvent(t, {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true}));
  }, 600);
  return 'ok';
})()""" % (json.dumps(text), json.dumps(list(SEND_PRIORITY)))


FOCUS_JS = r"""(() => {
  const vis = e => e && e.offsetParent !== null;
  const pref = Array.from(document.querySelectorAll('.ql-editor[contenteditable="true"], #prompt-textarea, textarea#chat-input, textarea.message-input-textarea, .ProseMirror[contenteditable="true"]')).filter(vis);
  const boxes = pref.length ? pref : Array.from(document.querySelectorAll('textarea, [contenteditable="true"]')).filter(vis);
  const box = boxes[boxes.length - 1];
  if (!box) return 'no-box';
  box.focus();
  if (box.tagName === 'TEXTAREA') { box.select(); } else { document.execCommand('selectAll', false, null); }
  return 'ok';
})()"""


def click_js() -> str:
    """JS: centre {x, y} of the best enabled send button near the focused box (JSON), or 'none'. The click itself is
    done by CDP Input.dispatchMouseEvent (a trusted browser-level click; the real mouse does not move).
    JS: центр найкращої кнопки надсилання біля поля (JSON) або 'none'. Сам клік — CDP (справжня миша не рухається)."""
    return r"""(() => {
  const PRI = %s, vis = e => e && e.offsetParent !== null;
  let area = document.activeElement || document.body;
  for (let k = 0; k < 8 && area.parentElement; k++) area = area.parentElement;
  for (const s of PRI) {
    const b = Array.from(area.querySelectorAll(s)).find(e => vis(e) && !e.disabled && e.getAttribute('aria-disabled') !== 'true');
    if (b) { const r = b.getBoundingClientRect(); return JSON.stringify({x: r.left + r.width / 2, y: r.top + r.height / 2}); }
  }
  return 'none';
})()""" % json.dumps(list(SEND_PRIORITY + ('div[class*="right-button-send"]', 'span.icon-send')))


JS_CLICK_JS = r"""(() => {
  const PRI = %s, vis = e => e && e.offsetParent !== null;
  let area = document.activeElement || document.body;
  for (let k = 0; k < 8 && area.parentElement; k++) area = area.parentElement;
  for (const s of PRI) {
    const b = Array.from(area.querySelectorAll(s)).find(e => vis(e) && !e.disabled && e.getAttribute('aria-disabled') !== 'true');
    if (b) { for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup'])
               b.dispatchEvent(new MouseEvent(t, {bubbles: true, cancelable: true, view: window}));
             b.click(); return 'js'; }
  }
  return 'none';
})()""" % json.dumps(list(SEND_PRIORITY + ('div[class*="right-button-send"]', 'span.icon-send')))


def _click(page, at: str) -> bool:
    try:
        c = json.loads(at)
    except (TypeError, ValueError):
        return False
    for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
        page.call("Input.dispatchMouseEvent", {"type": kind, "x": c["x"], "y": c["y"], "button": "left",
                                               "clickCount": 1 if kind != "mouseMoved" else 0})
    return True


LEFT_JS = r"""(() => { const e = document.activeElement;
  return e ? String(e.value !== undefined ? e.value : (e.innerText || '')).trim().length : 0; })()"""


def _enter(page):
    for kind in ("keyDown", "keyUp"):
        page.call("Input.dispatchKeyEvent", {"type": kind, "key": "Enter", "code": "Enter",
                                             "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13,
                                             **({"text": "\r"} if kind == "keyDown" else {})})


def send(page, text: str, sleep=time.sleep, wait_s: float = 30.0) -> str:
    """Type like a real keyboard (CDP Input.insertText; the real mouse/keyboard are not used), press Enter (CDP);
    if the text is still in the box, click the send button; if it is STILL there, RuntimeError (not sent).
    Ввести як клавіатура (CDP), натиснути Enter; якщо текст лишився в полі — натиснути кнопку; якщо й далі
    лишився — RuntimeError (не надіслано). Поле вводу чекаємо до wait_s секунд."""
    # The page must believe it is focused and visible (Qwen/DeepSeek send only from an active tab).
    # Сторінка має «вважати», що вона у фокусі й видима (Qwen і DeepSeek надсилають лише з активної вкладки).
    try:
        page.call("Emulation.setFocusEmulationEnabled", {"enabled": True})
        page.call("Page.setWebLifecycleState", {"state": "active"})
    except Exception:
        pass
    waited = 0.0
    while page.evaluate(FOCUS_JS) == "no-box":
        if waited >= wait_s:
            raise RuntimeError("chat input box not found / поле вводу не знайдено")
        sleep(2.0); waited += 2.0
    page.call("Input.insertText", {"text": text})
    sleep(0.8)
    _enter(page)
    sleep(1.5)
    if not page.evaluate(LEFT_JS):
        return "enter"
    _click(page, page.evaluate(click_js()))
    sleep(1.5)
    if not page.evaluate(LEFT_JS):
        return "clicked"
    page.evaluate(JS_CLICK_JS)                      # some sites react only to a page-level click / клік зі сторінки
    sleep(1.5)
    if not page.evaluate(LEFT_JS):
        return "clicked-js"
    raise RuntimeError("message was not sent (text left in the box) / повідомлення не надіслано")


def make_token(rng=random) -> str:
    """Unique marker for one question / Унікальна мітка одного запиту."""
    return f"[DANTE-{rng.randrange(10**8, 10**9)}]"


def after_token(body: str, token: str) -> str:
    """Page text after the LAST copy of the token ('' if absent) / Текст після останньої мітки."""
    i = (body or "").rfind(token)
    return "" if i < 0 else body[i + len(token):].strip()


def _norm(text: str) -> str:
    """NBSP -> space, drop zero-width spaces (Qwen's Monaco editor shows spaces as NBSP; live 25.11.2026).
    Нерозривні пробіли -> звичайні (редактор Monaco у Qwen показує пробіли як NBSP)."""
    return (text or "").replace("\u00a0", " ").replace("\u200b", "")


def _complete(text: str) -> bool:
    starts, ends = text.count("=== FILE:"), text.count("=== END FILE ===")
    return starts > 0 and ends >= starts


def ask(page, prompt: str, timeout: float = 300.0, stable_s: float = 30.0, interval: float = 3.0,
        sleep=time.sleep, now=time.monotonic, token: str | None = None, expect_files: bool = False) -> str:
    """Send `prompt` and return the answer text. With expect_files the prompt also gets CODE_BLOCK_RULE and the
    answer is read from code blocks after the token (exact text); it is accepted only when every FILE marker is
    closed and the text is the same for two reads, or (markers present but not closed) unchanged for 2*stable_s.
    Without expect_files any non-empty answer unchanged for stable_s is accepted. TimeoutError after `timeout`.
    Надіслати запит і повернути відповідь. З expect_files відповідь береться з блоків коду після мітки (точний текст)
    і приймається, лише коли всі файли закриті; без файлів — коли текст не змінюється stable_s секунд."""
    token = token or make_token()
    full = prompt + ("\n\n" + CODE_BLOCK_RULE if expect_files else "") + "\n\n" + token
    n0 = int(page.evaluate(PRE_COUNT_JS) or 0) if expect_files else 0
    send(page, full, sleep=sleep)
    start = now()
    last, same_since, same_reads = None, None, 0
    while True:
        sleep(interval)
        body = _norm(after_token(page.evaluate(BODY_JS) or "", token))
        text = body
        if expect_files:
            pre = _norm(page.evaluate(pre_after_token_js(token, n0)) or "")
            text = pre if "=== FILE:" in pre else body
        t = now()
        if text and text == last:
            same_reads += 1
            if expect_files:
                if _complete(text) and same_reads >= 2:
                    return text
                if "=== FILE:" in text and t - same_since >= 2 * stable_s:
                    return text
            elif t - same_since >= stable_s:
                return text
        else:
            last, same_since, same_reads = text, t, 0
        if t - start > timeout:
            raise TimeoutError(f"ask timeout, {len(text)} chars / час вийшов")
