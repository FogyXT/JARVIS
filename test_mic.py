"""TEST — faster-whisper (offline, no Google needed)"""
import speech_recognition as sr
import numpy as np
import io
import wave

r = sr.Recognizer()
r.dynamic_energy_threshold = False
r.energy_threshold = 300

mic = sr.Microphone(device_index=1)  # HyperX QuadCast
print(f"Mic: {mic}")
print("Prvé spustenie stiahne Whisper model (~1.5GB) — počkaj...")

from faster_whisper import WhisperModel
model = WhisperModel("tiny", device="cpu", compute_type="int8")  # tiny = najrýchlejší
print("✅ Model pripravený!")

with mic as source:
    r.adjust_for_ambient_noise(source, duration=1)
    r.energy_threshold = max(200, int(r.energy_threshold * 0.7))
    print(f"Threshold: {r.energy_threshold}")
    print("\n🎤 POVEDZ NIEČO (3s)...")
    audio = r.listen(source, timeout=5, phrase_time_limit=5)
    print("✅ Nahraté, transkribujem...")

# Konvertuj do formátu pre Whisper (16kHz mono float32)
raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
audio_np = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

segments, info = model.transcribe(audio_np, language="en")
text = " ".join(s.text for s in segments).strip()
print(f'🗣️ Rozpoznal som: "{text}"')
print(f"   Detekovaný jazyk: {info.language} (pravdepodobnosť {info.language_probability:.2f})")
print("✅ HOTOVO — Whisper funguje offline!")
