🇺🇦 [Українською](README.uk.md)

# DANTE — a program builder powered by free AI

**Dynamic Autonomous Neural Tool for Engineering.** DANTE writes, tests and assembles programs using free AI models and the resources of an ordinary Windows PC. Goal: a tool for people with few resources, enthusiasts and inventors.

> ⚠️ Experimental: the project is young and changes fast.

## What it can do
- **Writes code for a task** until the tests pass; every change can be undone.
- **Architect:** splits big work into steps (plan → approve → do).
- **Model hub:** Gemini, Groq, OpenRouter, NVIDIA, local Ollama models and more; an easy form to add new ones; **paid models only after a double confirmation of the amount**.
- **Learns from mistakes:** a lesson memory and night training while the PC is idle.
- **Reader (Vision):** takes code and whole conversations from AI web chats, detects the code language.
- **Swarm:** the Rust "ant" is a worker node for other PCs; coordinator and local-network discovery.
- **Remote and watchdog:** jobs through a folder, parallel work, overheating guard, self-restart.
- **Bilingual comments** in the code (English / Ukrainian).

## Requirements
Windows 10/11, Python 3.13 (standard library only), Rust for the ant. Free model keys are entered in the "+ Models" form.

## Run
```
python -m dante gui        # DANTE window
python -m dante selftest   # self-test
```

## Support the project

DANTE is free and is built at the author's own expense during the war in Ukraine. If it helps you, please support it:

- **Privat24 (card payment):** https://www.privat24.ua/send/kpaia (or the QR code below)
- **Bank transfer (IBAN, UAH):**
  - Recipient: YUSHCHENKO MYKOLA (ЮЩЕНКО МИКОЛА МИКОЛАЙОВИЧ)
  - IBAN: `UA183052990000026209884907769`
  - Payment purpose: Поповнення рахунку, ЮЩЕНКО МИКОЛА МИКОЛАЙОВИЧ

<img src="docs/donate-qr.png" width="200" alt="Privat24 QR">

Thank you! 💙💛
