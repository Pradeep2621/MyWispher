# 🎙️ MyWispher — Free, Local AI Voice Typing for Windows

> A free, open-source alternative to Wispr Flow. Press a key, speak, and your words appear instantly — anywhere on your screen.

---

## ✨ Features

- **Hold `F9`** to record, release to type *(push-to-talk)*
- **Press `F9` + `Space`** to lock hands-free, **press `F9` again** to finish
- **Local transcription** via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — no cloud, no latency
- **Optional LLM polish** via OpenRouter (toggle with `F8`) — fixes grammar, removes filler words
- **Animated overlay** — a subtle pulsing dot shows the app is live; expands to show recording/processing state
- **System tray icon** — right-click to toggle LLM, enable startup, open history log, or quit
- **History log** — every dictation saved to `history.log` with timestamp
- **Launch at Windows startup** — toggle from the tray menu

---

## 🖥️ How It Looks

```
[Idle]       ●  (tiny pulsing indigo dot, bottom-center of screen)

[Recording]  ╭──────────────────────────────╮
             │  🔴  ▂▄█▄▂  Recording       │
             ╰──────────────────────────────╯

[Processing] ╭──────────────────────────────╮
             │    ●  ●  ●    Processing     │
             ╰──────────────────────────────╯
```

---

## ⚡ Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Get a free OpenRouter API key
Sign up at [openrouter.ai](https://openrouter.ai) → copy your API key.

### 3. Create your `.env` file
```
OPENROUTER_API_KEY=your_key_here
```

### 4. Run it
```bash
pythonw wispher.py
```

Or double-click **`start.bat`** — no terminal window, runs silently in the background.

---

## ⌨️ Controls

| Key | Action |
|-----|--------|
| `F9` (hold) | Record while held, release to type |
| `F9` + `Space` | Lock into hands-free mode |
| `F9` (second press) | Stop locked recording & type |
| `F8` | Toggle LLM polish on/off |

---

## 🤖 Two Modes

### Mode 1 — Fast (default, LLM off)
`Audio → Whisper (local) → paste`

~0.3–0.5s latency. Pure speed, no API cost.

### Mode 2 — Smart (LLM on, press `F8`)
`Audio → Whisper → LLaMA 3.1 8B via OpenRouter → paste`

Fixes grammar, removes filler words, corrects technical terms. Slightly slower (~1s extra).

---

## 🛠️ Configuration

Edit the top of `wispher.py` to change:

```python
HOTKEY = keyboard.Key.f9     # recording key
LLM_TOGGLE = keyboard.Key.f8 # LLM toggle key
```

Customize the LLM's behaviour by editing `SYSTEM_PROMPT` — add your own domain-specific vocabulary corrections.

---

## 📝 History Log

Every dictation is saved to `history.log`:
```
[2026-02-21 22:22:45] I want to create a data pipeline that reads from SQL Server.
[2026-02-21 22:25:11] The Power BI dashboard needs a new DAX measure for rolling 30-day average.
```

Right-click tray → **Open History Log** to view it.

---

## 🚀 Launch at Startup

Right-click the tray icon → **"○ Launch at Windows Startup"** → done. It'll show ✅ when active.

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `faster-whisper` | Local speech-to-text (no internet needed) |
| `sounddevice` | Microphone recording |
| `pynput` | Global hotkey detection |
| `pystray` | System tray icon |
| `pyautogui` + `pyperclip` | Paste text into active window |
| `openai` | OpenRouter API client (for LLM polish) |
| `python-dotenv` | Load API key from `.env` |
| `Pillow` | Draw the tray and overlay icons |

---

## 🔒 Privacy

- Audio is processed **100% locally** by Whisper — never sent anywhere
- Only when LLM mode (`F8`) is ON does text leave your machine (sent to OpenRouter)
- Your API key stays in `.env` and is never committed to git

---

## 📄 License

MIT — do whatever you want with it.

---

*Built in one evening as a free alternative to Wispr Flow. If it helps you, consider starring the repo ⭐*
