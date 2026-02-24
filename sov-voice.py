#!/usr/bin/env python3
"""
sov-voice — sovereign system-wide STT
=======================================
Speak. It types. Anywhere your cursor is.

Uses faster-whisper locally (tiny model, CPU-fast on this machine).
No cloud. No subscription. Yours.

Usage:
  python3 sov-voice.py           # auto-detects silence, types result
  python3 sov-voice.py --push    # push-to-talk: hold Enter, release to transcribe
  python3 sov-voice.py --model base  # slightly more accurate, still fast
"""
import sys, os, time, subprocess, argparse, threading, queue
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

# ── CONFIG ────────────────────────────────────────────────────────────────────
SAMPLE_RATE   = 16000
CHANNELS      = 1
CHUNK         = 512          # samples per callback
SILENCE_DB    = -35          # dB threshold — below this = silence
SILENCE_SEC   = 1.2          # seconds of silence before transcribing
MIN_SPEECH    = 0.4          # ignore clips shorter than this (accidental noise)
MODEL_SIZE    = "tiny"       # tiny=fastest, base=better, small=best on CPU

# ── ANSI ──────────────────────────────────────────────────────────────────────
PINK = "\033[38;2;255;105;180m"
LIME = "\033[38;2;57;255;100m"
CYAN = "\033[38;2;0;220;255m"
GOLD = "\033[38;2;255;200;50m"
GRAY = "\033[38;2;85;85;105m"
RED  = "\033[38;2;255;70;70m"
RST  = "\033[0m"
BOLD = "\033[1m"

def rms_db(chunk):
    """RMS amplitude in dB."""
    rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2) + 1e-10)
    return 20 * np.log10(rms / 32768)

def type_text(text):
    """Type text at current cursor position system-wide."""
    display = os.environ.get("DISPLAY", ":0")
    text = text.strip()
    if not text:
        return
    try:
        # xdotool types at wherever the cursor currently is
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", "--delay", "0", "--", text],
            env={**os.environ, "DISPLAY": display},
            check=True
        )
    except Exception as e:
        # fallback: print it so you can at least copy it
        print(f"\n{GOLD}  [{text}]{RST}\n")

def load_model(size):
    print(f"  {GRAY}loading whisper {size} model...{RST}", end="", flush=True)
    model = WhisperModel(size, device="cpu", compute_type="int8")
    print(f"  {LIME}ready{RST}")
    return model

def transcribe(model, audio_np):
    segments, _ = model.transcribe(
        audio_np,
        language="en",
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
        beam_size=1,          # fastest
        best_of=1,
    )
    return " ".join(s.text for s in segments).strip()

# ── VAD MODE (auto — default) ─────────────────────────────────────────────────
def run_vad(model):
    print(f"\n{PINK}{BOLD}  sov-voice{RST}  {GRAY}listening — speak naturally, pause to transcribe{RST}")
    print(f"  {GRAY}Ctrl+C to quit{RST}\n")

    audio_buffer = []
    silence_start = None
    recording = False
    q = queue.Queue()

    def callback(indata, frames, time_info, status):
        q.put(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                        dtype='int16', blocksize=CHUNK, callback=callback):
        try:
            while True:
                chunk = q.get()
                db = rms_db(chunk)
                is_speech = db > SILENCE_DB

                if is_speech:
                    if not recording:
                        recording = True
                        audio_buffer = []
                        sys.stdout.write(f"\r  {RED}● recording{RST}   ")
                        sys.stdout.flush()
                    silence_start = None
                    audio_buffer.append(chunk)

                elif recording:
                    audio_buffer.append(chunk)
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= SILENCE_SEC:
                        # silence detected — transcribe
                        recording = False
                        audio_np = np.concatenate(audio_buffer).flatten().astype(np.float32) / 32768.0
                        duration = len(audio_np) / SAMPLE_RATE

                        if duration >= MIN_SPEECH:
                            sys.stdout.write(f"\r  {CYAN}◎ thinking...{RST}   ")
                            sys.stdout.flush()
                            text = transcribe(model, audio_np)
                            if text:
                                sys.stdout.write(f"\r  {LIME}✓ {text[:60]}{RST}\n")
                                sys.stdout.flush()
                                type_text(text)
                            else:
                                sys.stdout.write(f"\r  {GRAY}(nothing){RST}\n")
                                sys.stdout.flush()
                        else:
                            sys.stdout.write(f"\r  {GRAY}(too short){RST}\n")
                            sys.stdout.flush()

                        audio_buffer = []
                        silence_start = None
                        sys.stdout.write(f"  {GRAY}listening...{RST}   ")
                        sys.stdout.flush()

        except KeyboardInterrupt:
            print(f"\n\n{GRAY}  ✦  sov-voice out{RST}\n")

# ── PUSH-TO-TALK MODE ─────────────────────────────────────────────────────────
def run_push(model):
    print(f"\n{PINK}{BOLD}  sov-voice{RST}  {GRAY}push-to-talk mode{RST}")
    print(f"  {GRAY}press Enter to record → Enter again to transcribe → Ctrl+C to quit{RST}\n")

    try:
        while True:
            input(f"  {GOLD}[ hold Enter to record ]{RST} ")
            audio_buffer = []
            q = queue.Queue()
            stop_flag = threading.Event()

            def callback(indata, frames, time_info, status):
                if not stop_flag.is_set():
                    q.put(indata.copy())

            sys.stdout.write(f"\r  {RED}● recording — Enter to stop{RST}   ")
            sys.stdout.flush()

            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                                dtype='int16', blocksize=CHUNK, callback=callback):
                input()   # wait for Enter
                stop_flag.set()

            # drain queue
            while not q.empty():
                audio_buffer.append(q.get())

            if not audio_buffer:
                continue

            audio_np = np.concatenate(audio_buffer).flatten().astype(np.float32) / 32768.0
            duration = len(audio_np) / SAMPLE_RATE

            if duration < MIN_SPEECH:
                print(f"  {GRAY}(too short){RST}")
                continue

            sys.stdout.write(f"\r  {CYAN}◎ transcribing ({duration:.1f}s)...{RST}   ")
            sys.stdout.flush()

            text = transcribe(model, audio_np)
            if text:
                print(f"\r  {LIME}✓ {text[:80]}{RST}   ")
                type_text(text)
            else:
                print(f"\r  {GRAY}(nothing heard){RST}   ")

    except KeyboardInterrupt:
        print(f"\n\n{GRAY}  ✦  sov-voice out{RST}\n")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="sov-voice — sovereign STT")
    parser.add_argument("--push",  action="store_true", help="push-to-talk mode")
    parser.add_argument("--model", default=MODEL_SIZE,  help="whisper model size (tiny/base/small)")
    args = parser.parse_args()

    print(f"\n{PINK}{BOLD}  sov-voice  ·  sovereign STT{RST}")
    print(f"  {GRAY}model:{RST} {LIME}{args.model}{RST}   {GRAY}device: cpu  ·  local  ·  zero cloud{RST}\n")

    model = load_model(args.model)

    if args.push:
        run_push(model)
    else:
        run_vad(model)

if __name__ == "__main__":
    main()
