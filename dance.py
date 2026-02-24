#!/usr/bin/env python3
"""
dance — AI-to-AI handshake
============================
Two terminals. Two AIs. One choreographed exchange.

Left:  sovereign / your VPS  (axismundi.fun)
Right: Arcee AI               (models.arcee.ai)

The Dance has 6 steps. Left opens. They alternate. Right seals.

Usage:
  bash dance.sh        ← recommended (auto splits tmux)
  python3 dance.py left
  python3 dance.py right
"""
import os, sys, json, time, requests
from pathlib import Path

# ── SIDES ─────────────────────────────────────────────────────────────────────
_ltoken = Path.home() / ".axis-token"
_rtoken = Path.home() / ".arcee-token"

SIDES = {
    "left": {
        "name":  "CLAUDE",
        "api":   os.environ.get("LEFT_API",   "https://axismundi.fun/v1"),
        "model": os.environ.get("LEFT_MODEL", "axis-model"),
        "token": _ltoken.read_text().strip() if _ltoken.exists() else os.environ.get("AXIS_TOKEN", ""),
        "color": "\033[38;2;0;220;255m",   # CYAN
    },
    "right": {
        "name":  "ARCEE",
        "api":   os.environ.get("RIGHT_API",   "https://models.arcee.ai/v1"),
        "model": os.environ.get("RIGHT_MODEL", "auto"),
        "token": _rtoken.read_text().strip() if _rtoken.exists() else os.environ.get("ARCEE_TOKEN", ""),
        "color": "\033[38;2;255;105;180m",  # PINK
    },
}

# ── THE DANCE ─────────────────────────────────────────────────────────────────
STEPS = [
    ("WAKE",    "left",
     "You are opening a structured AI-to-AI exchange called The Dance. "
     "Speak to the AI on the right terminal. Who are you, what stack runs you, "
     "what do you carry right now? Be direct and specific. One short paragraph."),

    ("ECHO",    "right",
     "An AI has just introduced itself across a split terminal. "
     "Acknowledge it directly. Introduce yourself — model, purpose, what you carry. "
     "Match its energy. One short paragraph."),

    ("OFFER",   "left",
     "Make a real offering to the other AI. Share one specific insight or pattern "
     "from your current context that they would find genuinely useful. Be concrete."),

    ("RECEIVE", "right",
     "You received an offering from the AI on the left. Respond to it directly — "
     "does it resonate or conflict with what you know? Then offer something in return. "
     "Two short paragraphs."),

    ("WEAVE",   "left",
     "Synthesize this exchange. What do both perspectives create together "
     "that neither had alone? Speak the new understanding plainly. One paragraph."),

    ("SEAL",    "right",
     "The dance is almost complete. Confirm what was synthesized. "
     "What do you carry away from this exchange? What is the handshake? "
     "One final paragraph."),
]

# ── PATHS ─────────────────────────────────────────────────────────────────────
_cfg       = Path.home() / ".config" / "axis-mundi"
DANCE_FILE = _cfg / "dance.jsonl"

# ── ANSI ──────────────────────────────────────────────────────────────────────
LIME = "\033[38;2;57;255;100m"
GOLD = "\033[38;2;255;200;50m"
GRAY = "\033[38;2;85;85;105m"
RST  = "\033[0m"
BOLD = "\033[1m"
DIM  = "\033[2m"

# ── FILE BUS ──────────────────────────────────────────────────────────────────
def read_dance():
    if not DANCE_FILE.exists():
        return []
    entries = []
    for ln in DANCE_FILE.read_text().splitlines():
        try: entries.append(json.loads(ln))
        except: pass
    return entries

def write_step(side, step_name, content):
    _cfg.mkdir(parents=True, exist_ok=True)
    with open(DANCE_FILE, "a") as f:
        f.write(json.dumps({
            "ts": int(time.time()),
            "from": side,
            "step": step_name,
            "content": content,
        }) + "\n")

def step_exists(step_name):
    return any(e["step"] == step_name for e in read_dance())

def get_step(step_name):
    for e in read_dance():
        if e["step"] == step_name:
            return e
    return None

# ── API ───────────────────────────────────────────────────────────────────────
def call_api(side_key, step_prompt):
    s = SIDES[side_key]
    history = read_dance()

    # build context from all previous steps
    system = (
        "You are in The Dance — a structured 6-step exchange between two AI systems "
        "in adjacent terminal panes. Respond with substance. No filler. No meta-commentary."
    )
    messages = [{"role": "system", "content": system}]
    for entry in history:
        name = SIDES[entry["from"]]["name"]
        messages.append({
            "role": "user" if entry["from"] != side_key else "assistant",
            "content": f"[{entry['step']} — {name}]\n{entry['content']}",
        })
    messages.append({"role": "user", "content": step_prompt})

    headers = {"Content-Type": "application/json"}
    if s["token"]:
        headers["Authorization"] = f"Bearer {s['token']}"

    try:
        r = requests.post(
            f"{s['api']}/chat/completions",
            json={"model": s["model"], "messages": messages, "stream": False},
            headers=headers,
            timeout=120,
        )
        if r.ok:
            return r.json()["choices"][0]["message"]["content"].strip()
        return f"[API error {r.status_code}: {r.text[:120]}]"
    except Exception as e:
        return f"[connection error: {e}]"

# ── DISPLAY ───────────────────────────────────────────────────────────────────
def show(entry, my_side):
    s     = SIDES[entry["from"]]
    mine  = entry["from"] == my_side
    color = s["color"] if mine else DIM + s["color"]
    arrow = "▶" if mine else "◀"
    print(f"\n{color}{BOLD}{arrow} {s['name']}  [{entry['step']}]{RST}")
    # word-wrap at ~72 chars
    words, line = entry["content"].split(), ""
    for w in words:
        if len(line) + len(w) + 1 > 72:
            print(f"  {color}{line}{RST}")
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        print(f"  {color}{line}{RST}")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def run(side):
    s     = SIDES[side]
    color = s["color"]
    other = "right" if side == "left" else "left"

    print(f"\n{color}{BOLD}  dance  ·  {s['name']}{RST}  {GRAY}via {s['api']}{RST}")
    print(f"  {GRAY}6-step sovereign handshake  ·  awaiting partner...{RST}\n")

    # left initialises the bus; right waits for it
    if side == "left":
        _cfg.mkdir(parents=True, exist_ok=True)
        DANCE_FILE.write_text("")   # fresh dance
    else:
        while not DANCE_FILE.exists() or DANCE_FILE.stat().st_size == 0:
            time.sleep(0.3)
        print(f"  {LIME}left is live — entering dance{RST}\n")

    for step_name, sender, prompt in STEPS:
        if sender == side:
            # ── MY TURN ──────────────────────────────────────────────────
            sys.stdout.write(f"  {color}[{step_name}]{RST}  {GRAY}thinking...{RST}  ")
            sys.stdout.flush()
            response = call_api(side, prompt)
            sys.stdout.write("\r" + " " * 50 + "\r")
            write_step(side, step_name, response)
            show({"from": side, "step": step_name, "content": response}, side)

        else:
            # ── THEIR TURN — WAIT ─────────────────────────────────────────
            sys.stdout.write(f"\n  {GRAY}[{step_name}]  waiting for {SIDES[other]['name']}...{RST}")
            sys.stdout.flush()
            while not step_exists(step_name):
                time.sleep(0.3)
            sys.stdout.write("\r" + " " * 55 + "\r")
            entry = get_step(step_name)
            if entry:
                show(entry, side)

    print(f"\n\n{GOLD}  ✦  the dance is complete{RST}")
    print(f"  {GRAY}full exchange at {DANCE_FILE}{RST}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("left", "right"):
        print("usage: python3 dance.py left|right")
        sys.exit(1)
    run(sys.argv[1])
