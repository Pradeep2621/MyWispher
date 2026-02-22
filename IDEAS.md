# MyWispher — Future Ideas & Improvement Backlog

A running list of ideas discussed but not yet implemented.
Add new ideas here as they come up.

---

## 🚀 High Priority / High Impact

### 1. Chunked Background Transcription (Streaming ASR)
**Problem:** For long recordings (30s+), the post-stop wait is noticeable (~8-10s on CPU).
**Idea:** Transcribe audio in the background while the user is still talking, so by the time
they stop, most of the work is already done.

**How it would work:**
- Monitor the audio buffer continuously during recording
- Detect silence gaps ≥ 400ms as natural chunk boundaries (user pauses between sentences)
- On each silence gap, grab the buffered audio and spawn a background transcription thread
  with an index number (to preserve order)
- On stop, transcribe only the final small remainder (~1-2s)
- Assemble all results in order → single paste at the end (no mid-stream pasting)

**Expected gain:** Post-stop latency drops from ~10s → ~2s for a 30-second recording.

**Trade-offs to consider:**
| Approach | Pros | Cons |
|----------|------|------|
| Fixed-size chunks (every 6s) | Simple to implement | Can split words mid-syllable |
| Silence-based chunks ✅ | Clean word boundaries, natural for dictation | Needs silence detection |
| Overlap chunks (1s overlap) | Best accuracy | More complex, slight duplication risk |

**Recommended approach:** Silence-based chunking.
faster-whisper on CPU transcribes 6s of audio in ~1.5s, so background threads easily keep pace.

**Why deferred:** Not needed for short dictations. Revisit if recordings frequently exceed 15-20s.

---

## 🟡 Medium Priority / Nice to Have

### 2. Auto-paste Toggle (Copy-only Mode)
**Problem:** Some apps/fields don't accept `Ctrl+V` (e.g., certain web inputs, remote desktops).
**Idea:** Add a tray menu toggle — **"Auto-paste: ON/OFF"**.
- When OFF: text is still transcribed and copied to clipboard, but not auto-pasted.
- User manually pastes wherever they want.

**Implementation:** Simple boolean flag `AUTOPASTE = True`, toggle via tray menu item.

---

### 3. Configurable Hold Threshold
**Problem:** `HOLD_THRESHOLD = 0.5s` (tap vs. hold distinction) is hardcoded.
Some people tap faster or slower naturally.
**Idea:** Read from `.env` file — `HOLD_THRESHOLD_MS=500` — so the user can tune
it without touching code.

**Implementation:** `HOLD_THRESHOLD = int(os.getenv("HOLD_THRESHOLD_MS", 500)) / 1000`

---

### 4. Hot-reload Custom Dictionary
**Problem:** After editing `custom_dict.txt`, the app must be restarted to apply changes.
**Idea:** Add a **"Reload Dictionary"** tray menu item that calls `_load_custom_dict()`
and updates `CUSTOM_DICT` at runtime — no restart needed.

**Implementation:** Make `CUSTOM_DICT` a module-level variable reassigned on reload.

---

### 5. Per-app Language / Model Profile
**Problem:** You might want `small.en` for technical dictation and `tiny.en` for quick notes.
**Idea:** Detect the currently focused window's process name and auto-switch Whisper model
or apply a different custom dict profile.
- e.g., VS Code → `small.en` + coding-focused dict
- e.g., WhatsApp → `tiny.en` + casual dict

---

## 🟢 Low Priority / Exploratory

### 6. GPU Acceleration
**Problem:** All transcription currently runs on CPU (`device="cpu"`, `compute_type="int8"`).
**Idea:** Auto-detect CUDA/ROCm and switch to GPU if available.
`WhisperModel(model, device="cuda", compute_type="float16")`
This would cut transcription time by 5-10x.

**Note:** Requires `faster-whisper` GPU dependencies and a compatible GPU.

---

### 7. Transcription History Viewer
**Problem:** `history.log` is a plain text file opened in Notepad.
**Idea:** A small local HTML page (or simple Tkinter window) that shows the log
as a searchable, formatted list with timestamps. Accessible from the tray menu.

---

### 8. Punctuation Voice Commands
**Idea:** Recognise spoken punctuation commands and convert them:
- "period" / "full stop" → `.`
- "comma" → `,`
- "new line" → `\n`
- "new paragraph" → `\n\n`
- "question mark" → `?`

Applied as a second-pass regex after Whisper transcription, before LLM.

---

### 9. Multi-language Support
**Problem:** `language="en"` is hardcoded in the transcription call.
**Idea:** Add a language selector in the tray menu. Selecting a non-English language
also switches to a multilingual Whisper model (`medium`, `large-v3`).

---

*Last updated: 2026-02-22*
