# How to add a new AI model to DANTE

[Українська версія](MODELS.uk.md)

DANTE works with any OpenAI-compatible service and with models running on your own PC (Ollama, LM Studio). Adding a model takes a few clicks, no programming.

## Way 1. The "+ Models" window (recommended)

1. Start DANTE (`Dante.bat`) and press **"+ Models"** or **Ctrl+M**.
2. Press **"New"**.
3. Choose a **Service**. DANTE fills in the address and the key name:

   | Service | Key | Get a key |
   |---|---|---|
   | Ollama — model on this PC | none | https://ollama.com/library |
   | LM Studio — model on this PC | none | https://lmstudio.ai |
   | Google Gemini | `GEMINI_API_KEY` | https://aistudio.google.com/apikey |
   | Groq | `GROQ_API_KEY` | https://console.groq.com/keys |
   | OpenRouter | `OPENROUTER_API_KEY` | https://openrouter.ai/keys |
   | NVIDIA build | `NVIDIA_API_KEY` | https://build.nvidia.com |
   | Cerebras | `CEREBRAS_API_KEY` | https://cloud.cerebras.ai |
   | SambaNova | `SAMBANOVA_API_KEY` | https://cloud.sambanova.ai |
   | Mistral | `MISTRAL_API_KEY` | https://console.mistral.ai/api-keys |
   | Cohere | `COHERE_API_KEY` | https://dashboard.cohere.com/api-keys |
   | Hugging Face | `HF_TOKEN` | https://huggingface.co/settings/tokens |
   | Own service (OpenAI-compatible) | your own | you type the address |

4. Press **"Get a key"**, sign up on the service's page (you do this yourself), create a key and copy it.
5. Paste it into **"Key"**. It is stored only in `keys.txt` on your PC — never sent anywhere, never published.
6. Press **"Get list"** (free) and pick a model.
7. **"Name in DANTE"** is filled in automatically; you may change it.
8. Press **"Check"** — one tiny request shows whether the model answers and how fast.
9. Press **"Save"**. The model appears with a ★ and DANTE starts using it.

Marks: ✓ key set · - no key · $ paid · ★ yours.

## Paid models — no surprise costs

- "Own service" is marked **paid** by default, to be safe; a paid model needs its prices (USD per 1M tokens in/out).
- "Check" never calls a paid model. DANTE spends no money without your double confirmation with the amount; by default only free models are used.

## Way 2. A model on your own PC (offline)

Install **Ollama** or **LM Studio**, download a model (e.g. `ollama pull qwen2.5-coder:7b`), then choose that service in "+ Models" → Get list → Check → Save. `python -m dante setup` shows which local models fit your hardware.

## Way 3. By hand (advanced)

Your models are in `models.json` next to the `dante` folder; keys are in `keys.txt` as `NAME=value` lines:

```json
{"models": [
  {"name": "cerebras-llama", "base_url": "https://api.cerebras.ai/v1", "model": "llama-3.3-70b",
   "key_env": "CEREBRAS_API_KEY", "needs_key": true, "paid": false, "price_in": 0, "price_out": 0}
]}
```

Name: lowercase Latin letters, digits and hyphens (2–31 chars). Address: `https://…` or `http://localhost…` / `http://127.0.0.1…`.

## Check all models

Double-click `keys.bat`, or run `python -m dante models` and `python -m dante ping`.

## Safety

Never share `keys.txt`. DANTE's secret scan keeps it off GitHub. If a key leaks, delete it on the service's site and create a new one.
