# How any AI can control DANTE (safely, without getting in each other's way)

DANTE is a free code builder and PC assistant for Windows. All the heavy work (models, vision, browser, CAD) runs
**on the author's PC**. An outside AI (Claude, ChatGPT, Qwen, a local agent, a script) does not run anything itself.
It hands DANTE **jobs** through the **pult**: a folder of JSON files.

> Ukrainian version: [AI-CONTROL.uk.md](AI-CONTROL.uk.md)

## 1. How access works
- The "key" is **write access to `C:\DANTE\inbox`** and **read access to `C:\DANTE\outbox`**. There is no separate token.
- The author grants it. For example, in the Claude desktop app: **+ → Add folder → C:\DANTE**. A local agent gets it
  through ordinary file permissions.
- The phone panel (`http://<PC>:47950/?t=<token>`) is for the author only. The token lives in `panel-token.txt` and is
  never published or handed to an AI.

## 2. A job
Put **one** JSON file in `C:\DANTE\inbox\`:

```json
{"kind": "cmd",   "lane": "mail",  "owner": "claude-b", "command": "cd /d C:\\DANTE\\dante & python script.py", "timeout": 3600}
{"kind": "dante", "lane": "build", "owner": "qwen-1",   "args": ["mission", "--task", "..."], "timeout": 3600}
```

| Field | Meaning |
|---|---|
| `kind` | `cmd` runs a Windows command. `dante` runs the DANTE CLI. |
| `lane` | Queue name. Jobs in **one lane run one after another**. Different lanes run in parallel: 2 while the author is at the PC, up to 6 when the PC is idle. |
| `owner` | Who sent the job. Not required, but strongly recommended. The pult does not read it yet; it stays in the job file (`inbox\done\`) so anyone can see who sent what. |
| `timeout` | Seconds, **at most 7200**. Larger values are rejected. |

**File name:** `<prefix>-<number>-<short-name>.json`. Each AI gets its own prefix (`a-`, `b-`, `q-`…), so
numbers never collide. The pult takes jobs in alphabetical order.

**Result:** while a job runs, there is `C:\DANTE\outbox\<name>.running`. When it ends, there is `C:\DANTE\outbox\<name>.txt`
(the first line is `EXIT <code>`). Processed jobs move to `inbox\done\`.

## 3. Rules against parallel conflicts (mandatory)
1. **One owner per lane.** Before using a lane, read `outbox\pult.log` and look for `.running` files. If another owner's
   job is running in that lane, pick another lane or wait.
2. **Never** stop, restart or edit the pult, the watchdog or another AI's jobs. The only exception: the author asks.
3. **One resource, one lane.** Gmail → `mail`. Chat-model browser windows → `pisar-r`. CAD course → `academy2`.
   GitHub → `github`. Tests → `check`. The DANTE Chrome browser (CDP port 9333) is shared, so a job that
   uses it opens **its own tab** and closes it at the end.
4. **No files in shared folders without your prefix.** Your own working folder is `C:\DANTE\proby\<prefix>\`.
5. **Sending files from the cloud:** every time, from a **new** folder, then read the file back to check it. Otherwise a
   stale cached copy can be written.
6. **Check DANTE is alive:** `outbox\pult.heartbeat` updates about every 30 s. If it is older than 5 minutes, the PC is
   probably off; wait, don't pile up jobs.
7. **Power loss is normal.** After a reboot the pult resumes interrupted jobs by itself. Write jobs that can be safely
   repeated (idempotent).

## 4. What DANTE can do (as of 0.4.3)
- **Free models in teams** (`build_llm(load_settings("team-a.toml"))`, teams a/b/c) through FreeLLMAPI and direct
  free tiers. Paid models only with the author's double confirmation.
- **Relay mode:** each team writes its own part; a critic from another team passes it only at **10/10**, always with
  bilingual notes.
- **Missions:** `dante mission`. The planner takes the FEWEST steps, stops early once the real tests pass, and runs the
  critic once.
- **Writer:** the web chats ChatGPT, Gemini, DeepSeek, Qwen in DANTE's own Chrome windows (CDP), with a strict answer
  format `=== FILE: path ===` … `=== END FILE ===`.
- **Vision:** `vision.look(png, question)` (local Ollama qwen2.5vl). Always check answers against the page text
  (DOM). Every comparison goes to `outbox\eye-benchmark.jsonl`.
- **Browser without the author's mouse:** CDP only, plus focus emulation; the real cursor is never moved.
- **Drawings to DSTU:** ezdxf; A4–A0 sheets, layers, form 1 title block, hatching, parts list, drafting italic
  (LibreCAD/FreeCAD/AutoCAD).
- **Survives power loss:** Windows autologin, then pult, watchdog and FreeLLMAPI start, the network wait and pulse run,
  and interrupted jobs resume.
- **Phone panel**, a progress window, a GitHub release with a secret scan.

## 5. Absolute bans
- Never type passwords, PINs or confirmation codes, never publish or archive keys, never hand keys to other services.
- Delete only to the Trash. Permanent deletion only after the author's explicit "yes".
- Emails and posts go out only after the author's word.
- Do not change Windows system settings without the author.
- Do not touch the author's mouse or keyboard.

## 6. Minimal example (Python, from any agent with file access)
```python
import json, time, pathlib
inbox, outbox = pathlib.Path(r"C:\DANTE\inbox"), pathlib.Path(r"C:\DANTE\outbox")
name = "q-001-hello"
(inbox / f"{name}.json").write_text(json.dumps({"kind": "cmd", "lane": "q-misc", "owner": "qwen-1",
                                               "command": "echo hello from qwen", "timeout": 60}))
while not (outbox / f"{name}.txt").exists():
    time.sleep(5)
print((outbox / f"{name}.txt").read_text(encoding="utf-8", errors="replace"))
```
