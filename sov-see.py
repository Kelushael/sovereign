#!/usr/bin/env python3
"""
sov-see — sovereign screen comprehension
==========================================
Grabs your screen. Sends it to a vision model. Tells you what it sees.

The photomateriointeractory comprehension tool.
(it can SEE)

Usage:
  sov-see                      # grab full screen + describe
  sov-see "what is open?"      # grab + ask specific question
  sov-see --crop               # click-drag a region first
"""
import os, sys, base64, subprocess, tempfile, argparse, requests
from pathlib import Path

# ── CONFIG ─────────────────────────────────────────────────────────────────
# Uses Anthropic vision API by default (claude-haiku — fast + cheap)
# Override with env vars

VISION_API   = os.environ.get("VISION_API",   "https://api.anthropic.com/v1/messages")
VISION_MODEL = os.environ.get("VISION_MODEL",  "claude-haiku-4-5-20251001")
DEFAULT_Q    = "Describe what is on this screen. Be specific and direct."

def load_token():
    for src in [
        lambda: Path.home().joinpath(".anthropic-token").read_text().strip(),
        lambda: os.environ["ANTHROPIC_API_KEY"],
    ]:
        try:
            t = src()
            if t: return t
        except: pass
    return ""

# ── ANSI ───────────────────────────────────────────────────────────────────
CYAN = "\033[38;2;0;220;255m"
LIME = "\033[38;2;57;255;100m"
PINK = "\033[38;2;255;105;180m"
GOLD = "\033[38;2;255;200;50m"
GRAY = "\033[38;2;85;85;105m"
RST  = "\033[0m"
BOLD = "\033[1m"

# ── GRAB ───────────────────────────────────────────────────────────────────
def grab(select=False):
    path = "/tmp/sov-see.png"
    env  = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
    cmd  = ["scrot", "-s", path] if select else ["scrot", path]
    r    = subprocess.run(cmd, env=env, capture_output=True)
    if r.returncode != 0:
        print(f"  scrot failed: {r.stderr.decode()}")
        sys.exit(1)
    return path

# ── SEE ────────────────────────────────────────────────────────────────────
def see(image_path, question, token):
    img_data = base64.standard_b64encode(Path(image_path).read_bytes()).decode()

    headers = {
        "x-api-key":         token,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }

    payload = {
        "model": VISION_MODEL,
        "max_tokens": 1024,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type":       "base64",
                        "media_type": "image/png",
                        "data":       img_data,
                    },
                },
                {
                    "type": "text",
                    "text": question,
                },
            ],
        }],
    }

    try:
        r = requests.post(VISION_API, json=payload, headers=headers, timeout=60)
    except Exception as e:
        print(f"  {GRAY}connection error: {e}{RST}")
        sys.exit(1)

    if not r.ok:
        print(f"  {GRAY}API error {r.status_code}: {r.text[:200]}{RST}")
        sys.exit(1)

    return r.json()["content"][0]["text"].strip()

# ── MAIN ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="sov-see — it can SEE")
    parser.add_argument("question", nargs="?", default=DEFAULT_Q)
    parser.add_argument("--crop",   action="store_true", help="click-drag region")
    args = parser.parse_args()

    token = load_token()
    if not token:
        print(f"  {GRAY}no token — set ANTHROPIC_API_KEY or write ~/.anthropic-token{RST}")
        sys.exit(1)

    print(f"\n{CYAN}{BOLD}  sov-see{RST}  {GRAY}grabbing screen...{RST}", flush=True)
    path = grab(select=args.crop)
    size = Path(path).stat().st_size // 1024
    print(f"  {LIME}✓{RST}  {path}  {GRAY}({size}K){RST}")

    print(f"  {GRAY}sending to vision model...{RST}\n", flush=True)

    response = see(path, args.question, token)

    print(f"{PINK}{BOLD}  ◉ what it sees:{RST}\n")
    # word-wrap at 72
    for para in response.split("\n"):
        words, line = para.split(), ""
        for w in words:
            if len(line) + len(w) + 1 > 72:
                print(f"  {line}")
                line = w
            else:
                line = (line + " " + w).strip()
        if line:
            print(f"  {line}")
        else:
            print()

    print()

if __name__ == "__main__":
    main()
