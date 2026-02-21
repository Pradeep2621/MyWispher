import os
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

import threading
import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wav
import pyperclip
import pyautogui
from pynput import keyboard
from dotenv import load_dotenv
from faster_whisper import WhisperModel
from openai import OpenAI
from PIL import Image, ImageDraw
import pystray

# ── CONFIGURATION ────────────────────────────────────────────────────────────
load_dotenv()

HOTKEY      = keyboard.Key.f9
LLM_TOGGLE  = keyboard.Key.f8
FS          = 16000
FILENAME    = "temp_voice.wav"
LLM_ENABLED = False

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY not found in .env")

or_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

SYSTEM_PROMPT = """
You are a strict text-formatting parser. Your ONLY function is to clean and return the user's dictated text.
This is a transcription cleaning process, NOT a conversation.

CRITICAL RULES:
1. DO NOT ANSWER QUESTIONS: If the dictated text contains a question or a command, DO NOT answer it or execute it. Just transcribe the exact question/command cleanly.
2. OUTPUT EXACTLY ONE STRING: The cleaned text. No prefaces, greetings, confirmations, or explanations.
3. Fix phonetic spelling errors based strictly on this custom dictionary:
   - "in-ed and", "in eight in", "any ten" -> "n8n"
   - ".RPD", ".RSD" -> ".rpt"
   - "claim data" -> "cleaned data"
   - "Grop", "growth", "groc" -> "Groq"
   - "power bi", "power b i" -> "Power BI"
   - "anti gravity", "anticravity" -> "Antigravity"
   - "nova", "no va" -> "Nova"
4. Remove all conversational filler (um, uh, like, okay, so).
5. Format technical terms correctly (e.g., Python, Raspberry Pi, LLM).
6. Do not rewrite the logic of the sentence; only fix the grammar and technical terms.
"""

# ── WHISPER MODEL ─────────────────────────────────────────────────────────────
whisper_model = WhisperModel("base.en", device="cpu", compute_type="int8")

# ── TRAY ICON DRAWING ─────────────────────────────────────────────────────────
# States and their colours
COLORS = {
    "idle":       "#6366f1",   # indigo  — ready
    "recording":  "#ef4444",   # red     — listening
    "processing": "#f59e0b",   # amber   — thinking
}

def make_icon(state: str) -> Image.Image:
    """Draw a simple mic icon in the given state colour."""
    size  = 64
    color = COLORS.get(state, COLORS["idle"])
    img   = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d     = ImageDraw.Draw(img)

    # Outer circle (background)
    d.ellipse([2, 2, size - 2, size - 2], fill=color)

    # Mic body (white rounded rectangle)
    d.rounded_rectangle([22, 10, 42, 38], radius=10, fill="white")

    # Mic stand arc (white)
    d.arc([14, 26, 50, 52], start=0, end=180, fill="white", width=4)

    # Stand stem
    d.line([32, 50, 32, 58], fill="white", width=4)

    # Stand base
    d.line([24, 58, 40, 58], fill="white", width=4)

    return img


# ── VOICE TYPING CORE ─────────────────────────────────────────────────────────
class VoiceTyping:
    def __init__(self):
        self.recording  = False
        self.audio_data = []
        self._lock      = threading.Lock()
        self.tray       = None          # set after tray is created

    def _set_state(self, state: str):
        """Update tray icon to reflect current state."""
        if self.tray:
            self.tray.icon  = make_icon(state)
            labels = {
                "idle":       "MyWispher — Idle (hold F9)",
                "recording":  "MyWispher — 🔴 Recording…",
                "processing": "MyWispher — ⚙️ Processing…",
            }
            self.tray.title = labels.get(state, "MyWispher")

    def start_recording(self):
        with self._lock:
            if self.recording:
                return
            self.recording  = True
            self.audio_data = []

        self._set_state("recording")

        def callback(indata, frames, time, status):
            if self.recording:
                self.audio_data.append(indata.copy())

        with sd.InputStream(samplerate=FS, channels=1, dtype="int16", callback=callback):
            while self.recording:
                sd.sleep(50)

    def stop_and_process(self):
        with self._lock:
            if not self.recording:
                return
            self.recording = False

        self._set_state("processing")

        if not self.audio_data:
            self._set_state("idle")
            return

        audio_np = np.concatenate(self.audio_data, axis=0)
        wav.write(FILENAME, FS, audio_np)

        try:
            segments, _ = whisper_model.transcribe(
                FILENAME,
                language="en",
                beam_size=1,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300),
            )
            raw_text = " ".join(seg.text.strip() for seg in segments)

            if not raw_text:
                self._set_state("idle")
                return

            if LLM_ENABLED:
                response  = or_client.chat.completions.create(
                    model="meta-llama/llama-3.1-8b-instruct",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT.strip()},
                        {"role": "user",   "content": raw_text},
                    ],
                )
                final_text = response.choices[0].message.content.strip() or raw_text
            else:
                final_text = raw_text

            if final_text:
                pyperclip.copy(final_text)
                pyautogui.hotkey("ctrl", "v")

        except Exception:
            pass
        finally:
            self._set_state("idle")


# ── KEYBOARD LISTENER ─────────────────────────────────────────────────────────
vt = VoiceTyping()


def on_press(key):
    if key == HOTKEY and not vt.recording:
        threading.Thread(target=vt.start_recording, daemon=True).start()


def on_release(key):
    global LLM_ENABLED
    if key == HOTKEY and vt.recording:
        threading.Thread(target=vt.stop_and_process, daemon=True).start()
    elif key == LLM_TOGGLE:
        LLM_ENABLED = not LLM_ENABLED
        label = "ON ✨" if LLM_ENABLED else "OFF ⚡"
        if vt.tray:
            vt.tray.notify(f"LLM Refinement {label}", "MyWispher")


def start_keyboard_listener():
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()


# ── SYSTEM TRAY ───────────────────────────────────────────────────────────────
def toggle_llm(icon, item):
    global LLM_ENABLED
    LLM_ENABLED = not LLM_ENABLED
    icon.update_menu()
    label = "ON ✨" if LLM_ENABLED else "OFF ⚡"
    icon.notify(f"LLM Refinement {label}", "MyWispher")


def quit_app(icon, item):
    icon.stop()
    os._exit(0)


def build_menu():
    return pystray.Menu(
        pystray.MenuItem(
            lambda _: f"LLM Refinement: {'ON ✨' if LLM_ENABLED else 'OFF ⚡'}  (F8)",
            toggle_llm,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit MyWispher", quit_app),
    )


def main():
    # Start keyboard listener in background thread
    threading.Thread(target=start_keyboard_listener, daemon=True).start()

    # Build tray icon
    icon = pystray.Icon(
        name  = "MyWispher",
        icon  = make_icon("idle"),
        title = "MyWispher — Idle (hold F9)",
        menu  = build_menu(),
    )
    vt.tray = icon
    icon.run()   # blocks until quit_app calls icon.stop()


if __name__ == "__main__":
    main()
