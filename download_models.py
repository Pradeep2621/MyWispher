"""
download_models.py — Run this once to pre-download all Whisper models.
After this, switching models in MyWispher is instant (no waiting).
"""
import os
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"

from faster_whisper import WhisperModel

MODELS = ["tiny.en", "base.en", "small.en", "medium"]

print("📥 Pre-downloading all Whisper models...\n")
print("This only needs to run ONCE. Models are cached permanently.\n")

for name in MODELS:
    print(f"⏳ [{name}] Downloading...", flush=True)
    WhisperModel(name, device="cpu", compute_type="int8")
    print(f"✅ [{name}] Ready!\n", flush=True)

print("🎉 All models downloaded! Switch freely in MyWispher tray menu.")
input("\nPress Enter to close...")
