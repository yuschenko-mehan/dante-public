# DANTE: A Free AI Code Builder for Windows

Welcome to DANTE, a free AI code builder for Windows that acts as a "constructor of constructors." It turns a task into working, tested code using FREE AI models and your PC's own resources. Written by a Ukrainian college teacher who is not a programmer, DANTE follows the rule: "what DANTE can do, DANTE does." Claude (Anthropic) acts as the controller and reviewer, ensuring quality and accuracy. The project is written in Python (core, standard library mostly) and Rust (the swarm "Murakha" = "Ant"). Code comments are bilingual: English first, then Ukrainian. No license has been chosen yet (all rights reserved for now). Do NOT write MIT/Apache/GPL. For the Ukrainian version, see [FEATURES.uk.md](FEATURES.uk.md).

## What is DANTE

DANTE is a powerful tool designed to help you build software without needing to be an expert programmer. It uses advanced AI models to write code for you, based on your specifications. The core idea is simple: you describe what you want, and DANTE handles the technical details, writing the code, running tests, and fixing errors automatically. It is built entirely on free AI models, meaning you don't have to pay for expensive subscriptions to get started. The project is open in spirit, though currently all rights are reserved. It runs natively on Windows 10/11 x64, requires Python 3.13 and Git, and is optimized for a standard PC (like an i5-11400F with 16 GB RAM and a GeForce GT 1030).

## How it works

DANTE works by following a rigorous, test-driven process. First, specification tests are written—either by you or by Claude—to define exactly what the code should do. DANTE then uses free AI models to generate the code that passes these tests. It runs the tests immediately and, if they fail, it attempts to fix the code. In hard mode, it can try up to 5 times before giving up. Every failure becomes a valuable lesson. The tool supports two types of edits: whole file replacements (marked with `=== FILE: ===`) or precise PATCH edits (SEARCH/REPLACE) for existing files. To ensure efficiency, DANTE uses Graphify to build a map of your project, so every step sees only the relevant code without wasting tokens. Every run is logged in an audit JSONL file and committed to git. If a run fails, it is rolled back automatically to keep your workspace clean. Real-world performance on the author's PC shows that a task solved on the 1st try takes 30–70 seconds; on the 2nd try about 2 minutes; a failure costs 2–6 minutes (up to ~13 minutes with 5 attempts). About 40 tasks took about 40 minutes overnight.

## Free AI models and the wallet

DANTE supports a wide variety of free AI providers, giving you flexibility and choice. Supported providers include Gemini, Groq, OpenRouter (free models), NVIDIA, Cerebras, SambaNova, Mistral, Cohere, Hugging Face, GLM, and local Ollama models (dante-coder-3b ~9.9 tokens/s, 7b ~5.7 tokens/s on a GT 1030 PC). It also works with LM Studio and any OpenAI-compatible "own service" (for example FreeLLMAPI on 127.0.0.1). If a provider asks you to wait more than 15 seconds, DANTE switches to the next model at once. Routing is smart: DANTE picks models based on measured benchmark results. The wallet is designed to be free by default. Only free models are used unless you explicitly allow paid models. If you want to use a paid model, you must provide a price, set limits, and give TWO confirmations with the amount. Paid models are never pinged from the window to avoid accidental usage. Your API keys live only in `keys.txt` on your PC; they are never published, never packed into backups, and never travel over the swarm. You can add a provider and test a model using the `+ Models` form (Ctrl+M).

## Academy

The Academy is a powerful learning feature that helps DANTE improve. After a failed attempt, up to 3 other free models in parallel explain the cause of the error and give hints. The next attempt sees all these hints, significantly increasing the chance of success. The first result showed that a task failed twice with 5 attempts without the Academy, but succeeded on the 3rd attempt with it. You can switch off the Academy using the `--no-teacher` flag.

## Critic

The Critic is ON by default (switch it off with `--no-critic`). It acts as a second pair of eyes: a model scores a passing solution and lists any issues or improvements. This ensures the code is not just functional but also clean and robust.

## Contest

The Contest feature is OFF by default (switch it on with `--contest`). When enabled, several models solve the same task in parallel copies. The Critic then picks the best passing solution from the group. This is a great way to see different approaches and get the highest quality result.

## Learning from mistakes

DANTE learns from its mistakes to become better over time. It uses a `lessons.json` file. Before a task, DANTE reads relevant lessons from this file. After fixing its own error, it writes a new rule to the file. Claude's fixes are also added as lessons. This creates a growing knowledge base that helps DANTE avoid repeating the same mistakes. [PLANNED] future versions will include eternal learning in idle time, where DANTE will return to failed tasks and solve them again on its own.

## Architect

The Architect is the project management tool within DANTE. It allows you to split a project into steps, where each step involves at most 2 files. Every step sees the existing code, so DANTE doesn't lose context. You can plan, approve, do, undo, and view the history of changes. Any step can be undone, giving you full control over the development process.

## Reader and Collector

The Reader ("Vision") is a feature that reads code from AI chat pages in Chrome. It uses a separate Chrome profile called "DANTE" and the Chrome DevTools Protocol to assemble code blocks into files. This feature has passed live testing. [IN PROGRESS] The Collector is the next big idea: the main concept is that a conversation with any AI becomes files, which are then turned into tests and a build, step by step, into complete programs.

## Window and hotkeys

The DANTE window features a dark Windows 11 style with a Ukrainian and English interface. It includes a contrast slider ranging from 0 to 100 to accommodate different visual needs. You can also choose an optional drafting (GOST) font. Global hotkeys make navigation fast: `Ctrl+Alt+D` (Dante), `Ctrl+Alt+Q` (Quit), `Ctrl+Alt+Enter` (Run), `Ctrl+Alt+Z` (Undo), and `Ctrl+Alt+R` (Redo). Copy, paste, and cut work in ANY keyboard layout using `Ctrl+C`, `Ctrl+V`, `Ctrl+X`, and `Ctrl+A`, plus a right-click menu.

## Remote control: pult and phone panel

DANTE can be controlled remotely. The Pult is a folder-based system with an inbox and an outbox. Jobs are sent as JSON, organized into lanes, and include a queue forecast in `eta.txt`. It has timeouts that kill the whole process tree and supports only one pult at a time. It can start with Windows if you enable it. Notifications include pop-ups, sounds, and a `notifications.log` file. [WORKS] The Phone panel v2 is an adaptive interface for any screen, running in the local network and protected by a code.

## GitHub

DANTE integrates seamlessly with GitHub. You can connect your account using GitHub CLI to manage private or public repositories. Before publishing, DANTE scans the code and git history for keys to prevent accidental leaks. It generates a bilingual README and makes bilingual commits. A NEW repository is created only after you explicitly say "yes".

## Updates

Keeping DANTE up to date is easy. You can use the command `python -m dante update check | install | rollback | auto-on | auto-off`. Updates are downloaded from GitHub Releases only, and DANTE checks the SHA-256 checksum before installing. It keeps a backup and never touches your keys. [PLANNED] future versions will include a daily automatic check and a "new version" banner in the window.

## Swarm Murakha

The Swarm "Murakha" (Ant) is the heart of DANTE's distributed computing. Written in Rust, it consists of "Ants" that pull tasks from a coordinator. Ants do not have open ports; they discover each other automatically in the local network using UDP 47900. The system uses random back-off and per-ant random seeds to prevent collisions. Health monitoring and planning by reliability ensure that unreliable regions (weak internet, power cuts) get slow, non-urgent work. A Scout ant wanders along routes to find lost ants. Results are kept in a Mailbag until delivered. The coordinator state is replicated to ants; if the coordinator is destroyed, an ant can become the leader (self-healing). Tested on Windows. The "heart" of DANTE (its code, in 256 KB chunks with checksums) is spread across ants. You can restore DANTE from the swarm with `--restore-dante`, WITHOUT keys. Packages `murakha-0.3.0` and `0.4.0` for Windows x64 are available in Releases. [IN PROGRESS] The Swarm key feature will use a challenge-response handshake (HMAC-SHA256) and sign every line.

## Security

Security is a top priority for DANTE. [WORKS] Keys never leave your PC except by your own action. No passwords are ever typed by the AI. When publishing to GitHub, DANTE scans the code for secrets. [WORKS] Buttons "Keys → USB" and "Keys ← USB" save your keys and models to a flash drive, encrypted with AES-256-GCM (key derived from your passphrase with scrypt); the passphrase is typed only by you and is never stored. [IN PROGRESS] The same for the Rust swarm (ChaCha20-Poly1305 + Argon2id). [PLANNED] Architect flash drives (up to 3) can restore the Archant; once one has restored, another cannot.

## Roles: Archant, Reserve Archant, Knyaz, Ant, Standalone

Roles are chosen at installation (Install-DANTE.cmd), in Ukrainian or English. [WORKS]
- **Archant**: The owner's main DANTE, which commands the swarm.
- **Reserve Archant**: The owner's second device (laptop); it becomes the Archant only with the architect flash.
- **Knyaz** ("AdDante", "the hot one"): A friend's PC (Windows or Linux) that donates idle resources over the internet. It provides full CPU when idle, limited by temperature (pauses at the limit, continues after cooling by 10 °C; half power if no sensor). It only accepts orders signed by the Archant's Ed25519 key. Consent is one-time and can be withdrawn at any time. It runs in a sandbox, and results are kept on both sides with checksums. It works with or without a server and without a static address (direct, through any reachable swarm node, or a GitHub "mailbox"). The friend's GPU models can join the Academy. The friend's own API keys are never used.
- **Ant**: A light worker of the owner's swarm.
- **Standalone DANTE**: Just the builder, without the swarm.

## New on 23.11.2026
- [WORKS] Academy lesson before every mission.
- [WORKS] Vision 2: a local model (gemma3:4b, qwen2.5vl:3b via Ollama) describes pictures offline; the screen reader returns code, text or a physical description of objects from a screenshot of any window (covered by tests; live screen check is next).
- [WORKS] Progress window: a thin always-on-top bar shows what DANTE is doing; never takes focus, folds away.
- [WORKS] PC hardware: model, board, BIOS, CPU, RAM, GPU, disk; forecast of local models and parallel jobs; BIOS guide "power on after a blackout" for the board maker.
- [WORKS] Daily capacity check of free AI models (requests and tokens where the service reports them).
- [WORKS] Pult, watchdog and FreeLLMAPI start before anyone signs in to Windows.

## New on 20.11.2026
- [WORKS] Installer `Install-DANTE.cmd`: language, role, Python and Git, desktop shortcut, autostart, keys from a flash drive.
- [WORKS] Academy after two own mistakes: a model tries twice alone, then up to three other models give hints.
- [WORKS] Daily watch for new AI models; the critic proposes what is worth adding (keys are never added automatically).
- [IN PROGRESS] Writer: DANTE types a task into web AI chats (ChatGPT, Gemini, Qwen, DeepSeek, Mistral), waits for the answer and takes the code; a "relay" asks several chats at once and keeps the answer whose code passes the tests.
- [IN PROGRESS] Team work: parts of a big task go to groups of three different free models in parallel.
- [IN PROGRESS] Day / Night / As in Windows themes (Material Design 3 spirit, WCAG 2.2 AA contrast).

## Status: what works and what is in progress

Here is a summary of the current state of DANTE's features:

| Feature | Status |
| :--- | :--- |
| What is DANTE | [WORKS] |
| How it works | [WORKS] |
| Free AI models and the wallet | [WORKS] |
| Academy | [WORKS] |
| Critic | [WORKS] |
| Contest | [IN PROGRESS] |
| Learning from mistakes | [WORKS] |
| Architect | [WORKS] |
| Reader ("Vision") | [WORKS] |
| Collector | [IN PROGRESS] |
| Window and hotkeys | [WORKS] |
| Remote control: Pult | [WORKS] |
| Remote control: Phone panel v2 | [WORKS] |
| GitHub integration | [WORKS] |
| Updates | [WORKS] |
| Swarm "Murakha" | [WORKS] |
| Security: Keys never leave PC | [WORKS] |
| Security: keys on a USB drive | [WORKS] |
| Security: Architect flash drives | [PLANNED] |
| Roles and installer | [WORKS] |
| Installation docs | [WORKS] |
| One-click installer | [WORKS] |
| Daily update check | [PLANNED] |
| Eternal learning in idle | [PLANNED] |
| Swarm key handshake | [IN PROGRESS] |

## Requirements

To run DANTE, you need:
- **Operating System**: Windows 10 or 11 x64.
- **Python**: Version 3.13.
- **Git**: For version control integration.
- **Hardware**: A standard PC is sufficient. The author's PC (i5-11400F, 16 GB RAM, GeForce GT 1030) is enough to run the tool effectively.

For more information, visit the repository: https://github.com/yuschenko-mehan/dante-public
