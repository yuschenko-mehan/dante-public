# DANTE — a free AI program builder for Windows

[Українська версія](README.uk.md) · Version 0.4.1 · [Download (Releases)](https://github.com/yuschenko-mehan/dante-public/releases)

DANTE (Dynamic Autonomous Neural Tool for Engineering) is a Windows program that writes, tests and fixes code from your description. It runs on **free** AI models (cloud and local, on your own PC) and is made for people who are not programmers: you say what you need, DANTE does the work, and the tests show whether it is done.

The project rule: **"what DANTE can do, DANTE does"**. A person decides what to build and confirms important steps; the program does the routine.

Every feature below is marked honestly: **[WORKS]** — checked on a real PC; **[IN PROGRESS]** — code exists or is being written, not proven yet; **[PLANNED]** — a plan only.

## What DANTE can do

- **Writes code and checks it itself** [WORKS]. You give a task and tests (or DANTE prepares them with you). DANTE writes the code, runs the tests, sees the error, fixes it — several attempts until the tests pass. A failed attempt is fully rolled back, so your folder stays clean.
- **Academy** [WORKS]. Before every mission one teacher model gives a short lesson: the approach, the pitfalls, what the tests will check. If the main model fails twice, up to three other models look at the error at once and give hints.
- **Critic** [WORKS]. After a success another model rates the solution from 0 to 10 and lists remarks.
- **Learning from mistakes** [WORKS]. DANTE writes lessons to `lessons.json` and uses them in later tasks.
- **Architect** [WORKS]. Splits a big idea into small steps; you approve the plan, every step is saved in Git and can be undone.
- **Reader** [WORKS]. Takes code from AI chat pages in a separate Chrome profile — exactly, with indentation — and puts it into files, so generated code never has to be retyped.
- **Writer** [IN PROGRESS]. DANTE types a task into web AI chats (ChatGPT, Gemini, Qwen, DeepSeek, Mistral), waits for the answer and takes the code; a "relay" asks several chats at once and keeps the answer whose code passes the tests.
- **Pult and phone panel** [WORKS]. Jobs go through a "pult" folder; you can watch and control DANTE from a phone in your home network (with an access code).
- **Daily watch for new models** [WORKS]. DANTE compares model lists and proposes what is worth adding; it never adds keys by itself.
- **AI capacity check** [WORKS]. Daily: which free models answer and how many requests and tokens are left (where the service reports it).
- **PC hardware** [WORKS]. DANTE detects the PC model, motherboard, BIOS, CPU, RAM, graphics card and disk, predicts which local models fit and how many jobs to run at once, and gives a BIOS guide for "power on after a blackout" for the board maker.
- **Progress window** [WORKS]. A thin always-on-top bar shows what DANTE is doing now; click for details; it never takes the focus.
- **Team work** [IN PROGRESS]. Parts of a big task are done in parallel by groups of three different free models.
- **Vision 2** [WORKS]. A local model on your graphics card describes pictures offline. The screen reader takes a screenshot of any window and returns code (as files), text or a physical description of objects — material, size, forces, motion, risks [covered by tests, live screen check is next].
- **Window** [WORKS]. Ukrainian and English, big buttons, a red STOP, hotkeys, a contrast knob, a drafting font. Day / Night / As in Windows themes [IN PROGRESS].

Every part in detail: [docs/FEATURES.md](docs/FEATURES.md).

## Install

You need a PC with Windows 10 or 11 (64-bit) and internet for the first start.

1. Open **[Releases](https://github.com/yuschenko-mehan/dante-public/releases)** and download the newest `dante-<version>.zip`.
2. Unpack it into any folder (for example, Downloads).
3. Double-click **`Install-DANTE.cmd`**. The installer:
   - installs Python 3.13 and Git if needed (winget; Windows may ask for permission — click "Yes");
   - copies DANTE to `C:\DANTE\dante` (your keys, models and lessons are never overwritten);
   - asks for the language and the role;
   - makes the **DANTE** desktop shortcut and, for the Archant, the pult autostart;
   - offers to restore keys from a flash drive.
4. Open DANTE with the shortcut. No keys yet? Use **"+ Models"** (Ctrl+M) and the step-by-step guide in [docs/MODELS.md](docs/MODELS.md).

Manual install and updates: [docs/INSTALL.md](docs/INSTALL.md). Check the archive with the `.sha256` file next to it in Releases.

## Roles

The role is chosen during installation [WORKS — choosing and saving the role]:

- **Archant** — the owner's main DANTE: builds programs and leads the swarm.
- **Reserve Archant** — the owner's second device (for example, a laptop); a full DANTE that becomes the Archant only with the owner's flash drive.
- **Knyaz** — a friend's PC that donates idle resources and runs only orders signed by the Archant, with temperature control [IN PROGRESS: orders, consent and overheating guard are written, the Knyaz service is not].
- **Ant** — a light worker in your "Murakha" swarm (Rust) [WORKS in a local network].
- **Standalone DANTE** — just a program builder, no swarm.

## Free AI models

DANTE works with free cloud models (Gemini, Groq, OpenRouter, GLM and others), local models through Ollama (offline) and any OpenAI-compatible service, for example FreeLLMAPI on your own PC. If a model is overloaded, DANTE moves on to the next one. Routing picks models by measured results.

**Wallet** [WORKS]: free only by default. A paid model is used only if you set its price and limits and confirm the sum **twice**. Paid models are never pinged from the window.

## Keys on a USB drive

[WORKS] Model keys live only in `keys.txt` on your PC. The **"Keys → USB"** and **"Keys ← USB"** buttons save your keys and your model list to a flash drive, encrypted with AES-256-GCM; the encryption key comes from your passphrase (scrypt). Only you type the passphrase; it is never stored and cannot be recovered. Other files on the drive are not touched.

## Safety

- Keys are never published, never put into release archives and never sent through the swarm.
- Before publishing to GitHub, DANTE scans the code for forgotten keys.
- The AI never types your passwords; you sign in to services yourself.
- Tests you protect cannot be changed by DANTE.
- A failed attempt is rolled back; every Architect step can be undone.
- Swarm: a shared swarm key (HMAC) and Ed25519-signed orders for Knyaz PCs [IN PROGRESS].

## Status

| Part | Status |
|---|---|
| Builder, Academy, Critic, lessons, Architect | [WORKS] |
| Reader, pult, phone panel, updates, GitHub | [WORKS] |
| Installer, roles, keys on a USB drive, new-model watch | [WORKS] |
| Murakha (Rust) in a local network | [WORKS] |
| Vision 2, PC hardware, progress window, capacity check | [WORKS] |
| Writer, relay, team work, Day / Night themes | [IN PROGRESS] |
| Knyaz over the internet, Archant "crown" | [IN PROGRESS] |
| Voice, webcam, Arduino, 3D | [PLANNED] |

Full table: [docs/FEATURES.md](docs/FEATURES.md).

## Support the project

DANTE is free and is built at the author's own expense during the war in Ukraine. If it helps you, please support it:

- **Privat24 (card payment):** https://www.privat24.ua/send/kpaia (or the QR code below)
- **Bank transfer (IBAN, UAH):**
  - Recipient: YUSHCHENKO MYKOLA (ЮЩЕНКО МИКОЛА МИКОЛАЙОВИЧ)
  - IBAN: `UA183052990000026209884907769`
  - Payment purpose: Поповнення рахунку, ЮЩЕНКО МИКОЛА МИКОЛАЙОВИЧ

<img src="docs/donate-qr.png" width="200" alt="Privat24 QR">

Feedback, bug reports and ideas (the Issues tab) and telling friends and colleagues about DANTE help too.

Thank you! 💙💛
