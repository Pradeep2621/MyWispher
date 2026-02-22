import os
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

import threading, queue, math, subprocess, time, re, traceback
import tkinter as tk
import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wav
import pyperclip, pyautogui
from pynput import keyboard
from dotenv import load_dotenv
from faster_whisper import WhisperModel
from openai import OpenAI
from PIL import Image, ImageDraw
from datetime import datetime
import pystray

# ── CONFIG ────────────────────────────────────────────────────────────────────
load_dotenv()
HOTKEY_LABEL   = "Alt+Win"                        # push-to-talk combo label (for UI)
LLM_TOGGLE     = keyboard.Key.f8
HOLD_THRESHOLD = 0.5                             # seconds: tap=hands-free, hold=push-to-talk
FS             = 16000
FILENAME       = "temp_voice.wav"
LLM_ENABLED    = False
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
LOG_FILE       = os.path.join(BASE_DIR, "history.log")
STARTUP_LNK    = os.path.join(
    os.environ.get("APPDATA", ""),
    "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "MyWispher.lnk"
)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY not found in .env")

or_client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

SYSTEM_PROMPT = """
You are a strict text-formatting parser. Your ONLY function is to clean and return the user's dictated text.
This is a transcription cleaning process, NOT a conversation.

CRITICAL RULES:
1. DO NOT ANSWER QUESTIONS: If the dictated text contains a question or a command, DO NOT answer it or execute it. Just transcribe it cleanly.
2. OUTPUT EXACTLY ONE STRING: The cleaned text. No prefaces, greetings, confirmations, or explanations.
3. Remove all conversational filler (um, uh, like, okay, so).
4. Format technical terms correctly (e.g., Python, Raspberry Pi, LLM).
5. Do not rewrite the logic of the sentence; only fix grammar and technical terms.
"""

# ── WHISPER ───────────────────────────────────────────────────────────────────
WHISPER_MODELS  = ["tiny.en", "base.en", "small.en", "medium"]
CURRENT_MODEL   = "base.en"
whisper_model   = WhisperModel(CURRENT_MODEL, device="cpu", compute_type="int8")

# ── HISTORY LOG ───────────────────────────────────────────────────────────────
def _log(text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")

# ── CUSTOM PHONETIC DICTIONARY ───────────────────────────────────────────────
def _load_custom_dict() -> list[tuple[str, str]]:
    """Load phonetic corrections from custom_dict.txt. Edit freely; restart to apply."""
    path  = os.path.join(BASE_DIR, "custom_dict.txt")
    pairs: list[tuple[str, str]] = []
    if not os.path.exists(path):
        return pairs
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if " -> " in line:
                src, dst = line.split(" -> ", 1)
                pairs.append((src.strip(), dst.strip()))
    return pairs

def _apply_custom_dict(text: str) -> str:
    """Apply all phonetic corrections (case-insensitive)."""
    for src, dst in CUSTOM_DICT:
        text = re.sub(re.escape(src), dst, text, flags=re.IGNORECASE)
    return text

CUSTOM_DICT = _load_custom_dict()

# ── STARTUP HELPERS ───────────────────────────────────────────────────────────
def _startup_enabled() -> bool:
    return os.path.exists(STARTUP_LNK)

def _enable_startup():
    script = (
        f'$ws = New-Object -ComObject WScript.Shell; '
        f'$s = $ws.CreateShortcut("{STARTUP_LNK}"); '
        f'$s.TargetPath = "pythonw.exe"; '
        f'$s.Arguments = \'"{os.path.join(BASE_DIR, "wispher.py")}"\'; '
        f'$s.WorkingDirectory = "{BASE_DIR}"; '
        f'$s.Save()'
    )
    subprocess.run(["powershell", "-WindowStyle", "Hidden", "-Command", script],
                   capture_output=True)

def _disable_startup():
    try:
        os.remove(STARTUP_LNK)
    except FileNotFoundError:
        pass

# ── OVERLAY ───────────────────────────────────────────────────────────────────
class OverlayWindow:
    W, H   = 190, 38
    TRANSP = "#000001"
    PILL   = "#1a1a2e"

    def __init__(self, cmd_q: queue.Queue):
        self.q      = cmd_q
        self._anim  = None
        self._tick  = 0
        self._state = "idle"

        r = tk.Tk()
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.configure(bg=self.TRANSP)
        r.attributes("-transparentcolor", self.TRANSP)

        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.geometry(f"{self.W}x{self.H}+{(sw - self.W) // 2}+{sh - self.H - 110}")
        r.deiconify()

        self.cv   = tk.Canvas(r, width=self.W, height=self.H,
                              bg=self.TRANSP, highlightthickness=0)
        self.cv.pack()
        self.root = r
        r.after(50,  self._poll)
        r.after(10,  self._animate)

    def _poll(self):
        try:
            while True:
                self._handle(self.q.get_nowait())
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _handle(self, cmd):
        self._stop_anim()
        self._state = cmd
        self._tick  = 0
        self._animate()

    def _stop_anim(self):
        if self._anim:
            self.cv.after_cancel(self._anim)
            self._anim = None

    def _pill(self, color):
        W, H, r = self.W, self.H, self.H // 2
        self.cv.create_oval(0, 0, H, H, fill=color, outline="")
        self.cv.create_oval(W - H, 0, W, H, fill=color, outline="")
        self.cv.create_rectangle(r, 0, W - r, H, fill=color, outline="")

    def _animate(self):
        self.cv.delete("all")
        cy = self.H // 2

        if self._state == "idle":
            # Tiny breathing indigo dot
            pulse = 0.4 + 0.6 * abs(math.sin(self._tick * 0.055))
            rd    = int(2 + 1.5 * abs(math.sin(self._tick * 0.055)))
            cx    = self.W // 2
            rv = int(99 * pulse); gv = int(102 * pulse); bv = int(241 * pulse)
            self.cv.create_oval(cx - rd, cy - rd, cx + rd, cy + rd,
                                fill=f"#{rv:02x}{gv:02x}{bv:02x}", outline="")

        elif self._state == "recording":
            self._pill(self.PILL)
            pulse = 0.55 + 0.45 * abs(math.sin(self._tick * 0.14))
            rv    = int(239 * pulse)
            self.cv.create_oval(13, cy - 4, 21, cy + 4,
                                fill=f"#{rv:02x}2020", outline="")
            bw, gap, sx = 3, 3, 28
            for i in range(4):
                phase = self._tick * 0.18 + i * 1.0
                h     = 3 + int(9 * abs(math.sin(phase)))
                br    = 1.0 - abs(i - 1.5) * 0.1
                r2 = int(244 * br); g2 = int(63 * br); b2 = int(94 * br)
                x0 = sx + i * (bw + gap)
                self.cv.create_rectangle(x0, cy - h, x0 + bw, cy + h,
                                         fill=f"#{r2:02x}{g2:02x}{b2:02x}",
                                         outline="")
            self.cv.create_text(75, cy, text="Recording",
                                fill="#cbd5e1", font=("Segoe UI", 8), anchor="w")

        elif self._state == "processing":
            self._pill(self.PILL)
            dot_r, spacing = 3, 12
            sx = self.W // 2 - spacing - 28
            for i in range(3):
                phase = self._tick * 0.22 + i * 1.1
                y_off = int(4 * math.sin(phase))
                br    = 0.6 + 0.4 * abs(math.sin(phase))
                r3 = int(245 * br); g3 = int(158 * br); b3 = int(11 * br)
                cx = sx + i * spacing
                self.cv.create_oval(cx - dot_r, cy + y_off - dot_r,
                                    cx + dot_r, cy + y_off + dot_r,
                                    fill=f"#{r3:02x}{g3:02x}{b3:02x}", outline="")
            self.cv.create_text(self.W // 2 + 10, cy, text="Processing",
                                fill="#94a3b8", font=("Segoe UI", 8), anchor="w")

        elif self._state == "locked":
            self._pill("#150a2e")                          # deep purple pill
            pulse = 0.65 + 0.35 * abs(math.sin(self._tick * 0.05))
            pv = int(124 * pulse); gv2 = int(58 * pulse); bv2 = int(237 * pulse)
            self.cv.create_oval(13, cy - 4, 21, cy + 4,
                                fill=f"#{pv:02x}{gv2:02x}{bv2:02x}", outline="")
            self.cv.create_text(75, cy, text="Hands-free",
                                fill="#c4b5fd", font=("Segoe UI", 8, "bold"), anchor="w")

        self._tick += 1
        self._anim = self.cv.after(40, self._animate)

    def run(self):
        self.root.mainloop()


# ── VOICE TYPING ──────────────────────────────────────────────────────────────
class VoiceTyping:
    def __init__(self):
        self.recording     = False
        self.locked        = False   # True = hands-free lock mode
        self.audio_data    = []
        self._lock         = threading.Lock()
        self.tray          = None
        self.cmd_q: queue.Queue | None = None

    def _set_state(self, s: str):
        if self.cmd_q:
            self.cmd_q.put(s)
        if self.tray:
            c = {"idle": "#6366f1", "recording": "#ef4444",
                 "locked": "#7c3aed", "processing": "#f59e0b"}
            self.tray.icon  = _tray_icon(c.get(s, "#6366f1"))
            t = {"idle":       f"MyWispher [{CURRENT_MODEL}] — Idle (press Alt+Win)",
                 "recording":  f"MyWispher [{CURRENT_MODEL}] — 🔴 Recording…",
                 "locked":     f"MyWispher [{CURRENT_MODEL}] — 🔒 Hands-free…",
                 "processing": f"MyWispher [{CURRENT_MODEL}] — ⚙️ Processing…"}
            self.tray.title = t.get(s, "MyWispher")

    def start_recording(self):
        with self._lock:
            if self.recording: return
            self.recording  = True
            self.locked     = False
            self.audio_data = []

        self._set_state("recording")

        def cb(indata, frames, time, status):
            if self.recording:
                self.audio_data.append(indata.copy())

        with sd.InputStream(samplerate=FS, channels=1, dtype="int16", callback=cb):
            while self.recording:
                sd.sleep(50)

        self._process()

    def stop(self):
        """Stop recording and process (used by Alt/Win release or second Alt+Win press)."""
        self.recording = False

    def lock(self):
        """Lock into hands-free mode — tap Alt+Win while recording."""
        if self.recording:
            self.locked = True
            self._set_state("locked")

    def _process(self):
        self._set_state("processing")
        if not self.audio_data:
            self._set_state("idle"); return

        audio_np = np.concatenate(self.audio_data, axis=0)
        if len(audio_np) < FS // 2:
            self._set_state("idle"); return

        wav.write(FILENAME, FS, audio_np)
        try:
            segs, _ = whisper_model.transcribe(
                FILENAME, language="en", beam_size=1,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300))
            raw = " ".join(s.text.strip() for s in segs)
            if not raw:
                if self.tray:
                    self.tray.notify("Nothing heard — try again!", "MyWispher")
                self._set_state("idle"); return

            # Apply phonetic corrections from custom_dict.txt
            corrected = _apply_custom_dict(raw)

            if LLM_ENABLED:
                resp  = or_client.chat.completions.create(
                    model="meta-llama/llama-3.1-8b-instruct",
                    messages=[{"role": "system", "content": SYSTEM_PROMPT.strip()},
                               {"role": "user",   "content": corrected}])
                final = resp.choices[0].message.content.strip() or corrected
            else:
                final = corrected

            if final:
                _log(final)
                # Save clipboard → paste → restore clipboard
                prev_clip = ""
                try:
                    prev_clip = pyperclip.paste()
                except Exception:
                    pass
                pyperclip.copy(final)
                time.sleep(0.15)                 # let clipboard settle
                pyautogui.hotkey("ctrl", "v")
                def _restore(prev=prev_clip):
                    time.sleep(0.5)
                    try:
                        pyperclip.copy(prev)
                    except Exception:
                        pass
                threading.Thread(target=_restore, daemon=True).start()

        except Exception as e:
            err_msg = str(e)[:80]
            _log(f"ERROR: {err_msg}\n{traceback.format_exc()}")
            if self.tray:
                self.tray.notify(f"⚠️ Error: {err_msg}", "MyWispher")
        finally:
            self._set_state("idle")


# ── TRAY ICON ─────────────────────────────────────────────────────────────────
def _tray_icon(color: str) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    d.ellipse([2, 2, 62, 62], fill=color)
    d.rounded_rectangle([22, 10, 42, 38], radius=10, fill="white")
    d.arc([14, 26, 50, 52], start=0, end=180, fill="white", width=4)
    d.line([32, 50, 32, 58], fill="white", width=4)
    d.line([24, 58, 40, 58], fill="white", width=4)
    return img


vt = VoiceTyping()


# ── KEYBOARD ──────────────────────────────────────────────────────────────────
_pressed:    set   = set()
_press_time: float = 0.0

def _hotkey_active() -> bool:
    """True when Alt + Win are both currently held."""
    alt = any(k in _pressed for k in (
        keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r))
    win = any(k in _pressed for k in (
        keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r))
    return alt and win

def on_press(key):
    global LLM_ENABLED, _press_time
    was_inactive = not _hotkey_active()
    _pressed.add(key)

    if _hotkey_active() and was_inactive:
        if not vt.recording:
            # Combo just activated → start recording, note start time
            _press_time = time.monotonic()
            threading.Thread(target=vt.start_recording, daemon=True).start()
        elif vt.locked:
            # Second Alt+Win while locked → stop & process
            vt.stop()
    elif key == LLM_TOGGLE:
        LLM_ENABLED = not LLM_ENABLED
        if vt.tray:
            vt.tray.notify(
                f"LLM Refinement {'ON ✨' if LLM_ENABLED else 'OFF ⚡'}", "MyWispher")

def on_release(key):
    _pressed.discard(key)
    if not _hotkey_active() and vt.recording and not vt.locked:
        held = time.monotonic() - _press_time
        if held < HOLD_THRESHOLD:
            # Short tap → lock into hands-free mode
            vt.lock()
        else:
            # Long hold → push-to-talk: stop & type
            vt.stop()

def _kb_thread():
    with keyboard.Listener(on_press=on_press, on_release=on_release) as l:
        l.join()


# ── TRAY MENU ─────────────────────────────────────────────────────────────────
def _toggle_llm(icon, item):
    global LLM_ENABLED
    LLM_ENABLED = not LLM_ENABLED
    icon.update_menu()
    icon.notify(f"LLM {'ON ✨' if LLM_ENABLED else 'OFF ⚡'}", "MyWispher")

def _toggle_startup(icon, item):
    if _startup_enabled():
        _disable_startup()
        icon.notify("Removed from Windows startup", "MyWispher")
    else:
        _enable_startup()
        icon.notify("Added to Windows startup ✅", "MyWispher")
    icon.update_menu()

def _open_log(icon, item):
    if os.path.exists(LOG_FILE):
        os.startfile(LOG_FILE)
    else:
        icon.notify("No history yet — start dictating!", "MyWispher")

def _open_dict(icon, item):
    path = os.path.join(BASE_DIR, "custom_dict.txt")
    if os.path.exists(path):
        os.startfile(path)
    else:
        icon.notify("custom_dict.txt not found in app folder", "MyWispher")

def _quit(icon, item):
    icon.stop()
    os._exit(0)

def _switch_model(name):
    def _load():
        global whisper_model, CURRENT_MODEL
        # Load first — only update label once it's truly ready
        new_model      = WhisperModel(name, device="cpu", compute_type="int8")
        whisper_model  = new_model
        CURRENT_MODEL  = name
        if vt.tray:
            vt.tray.update_menu()
            vt._set_state("idle")   # refreshes tooltip with confirmed model name
    threading.Thread(target=_load, daemon=True).start()

def _make_model_item(name):
    def action(icon, item):
        if CURRENT_MODEL != name:
            _switch_model(name)
    return pystray.MenuItem(
        lambda _: f"{'✅' if CURRENT_MODEL == name else '○'} {name}",
        action
    )

def _menu():
    return pystray.Menu(
        pystray.MenuItem(
            lambda _: f"LLM Refinement: {'ON ✨' if LLM_ENABLED else 'OFF ⚡'}  (F8)",
            _toggle_llm),
        pystray.MenuItem(
            lambda _: f"{'✅' if _startup_enabled() else '○'} Launch at Windows Startup",
            _toggle_startup),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Whisper Model", pystray.Menu(
            *[_make_model_item(m) for m in WHISPER_MODELS]
        )),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open History Log", _open_log),
        pystray.MenuItem("Edit Custom Dictionary", _open_dict),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit MyWispher", _quit),
    )


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    cmd_q    = queue.Queue()
    overlay  = OverlayWindow(cmd_q)
    vt.cmd_q = cmd_q

    threading.Thread(target=_kb_thread, daemon=True).start()

    icon = pystray.Icon("MyWispher", _tray_icon("#6366f1"),
                        "MyWispher — Idle (press Alt+Win)", _menu())
    vt.tray = icon
    threading.Thread(target=icon.run, daemon=True).start()

    overlay.run()

if __name__ == "__main__":
    main()
