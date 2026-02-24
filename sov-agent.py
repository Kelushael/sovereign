#!/usr/bin/env python3
"""
sov-agent — sovereign computer use
=====================================
Sees your screen. Clicks. Types. Uses your terminal.
Runs on your iron. Reports to your model.

This is the sovereign answer to OpenAI computer use.

Usage:
  sov-agent "open a terminal and check disk space"
  sov-agent --watch          # continuous observe mode, no actions
  sov-agent --loop "task"    # keep going until task is done
"""
import os, sys, json, time, base64, subprocess, argparse, requests
from pathlib import Path

# ── CONFIG ─────────────────────────────────────────────────────────────────
VISION_API   = os.environ.get("VISION_API",  "https://api.anthropic.com/v1/messages")
VISION_MODEL = os.environ.get("VISION_MODEL", "claude-haiku-4-5-20251001")
DISPLAY      = os.environ.get("DISPLAY", ":0")
MAX_STEPS    = int(os.environ.get("SOV_AGENT_STEPS", "10"))

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
PINK = "\033[38;2;255;105;180m"; LIME = "\033[38;2;57;255;100m"
CYAN = "\033[38;2;0;220;255m";   GOLD = "\033[38;2;255;200;50m"
GRAY = "\033[38;2;85;85;105m";   RED  = "\033[38;2;255;70;70m"
RST  = "\033[0m"; BOLD = "\033[1m"

# ── EYES — grab screen ─────────────────────────────────────────────────────
def grab(path="/tmp/sov-agent.png"):
    env = {**os.environ, "DISPLAY": DISPLAY}
    subprocess.run(["scrot", "-o", path], env=env,
                   capture_output=True, timeout=5)
    return path

def encode(path):
    return base64.standard_b64encode(Path(path).read_bytes()).decode()

# ── BRAIN — ask vision model what it sees + what to do ────────────────────
def see_and_decide(image_path, task, history, token, observe_only=False):
    action_schema = "" if observe_only else """
After describing the screen, respond with a JSON action block:
```json
{
  "action": "click|type|key|scroll|shell|done|wait",
  "x": 100,
  "y": 200,
  "text": "text to type",
  "key": "ctrl+t",
  "command": "shell command to run",
  "reason": "why this action"
}
```
Actions:
- click: left-click at x,y
- type: type text at current cursor
- key: send keypress (e.g. "ctrl+t", "Return", "ctrl+l")
- scroll: scroll at x,y (use "direction": "up"/"down")
- shell: run a shell command (use sparingly)
- wait: pause and re-observe
- done: task complete, explain result
"""

    system = f"""You are a computer use agent running on a sovereign Linux desktop.
You see the screen and control the machine to complete tasks.
Be precise. Take one action at a time. Observe the result.
Current task: {task}
{action_schema}"""

    history_msgs = []
    for h in history[-6:]:  # last 6 steps for context
        history_msgs.append({"role": h["role"], "content": h["content"]})

    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": encode(image_path),
            },
        },
        {
            "type": "text",
            "text": "What do you see? What is the current state? What action should be taken next?" if not observe_only
                    else "Describe what you see on the screen in detail.",
        },
    ]

    headers = {
        "x-api-key": token,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    payload = {
        "model": VISION_MODEL,
        "max_tokens": 1024,
        "system": system,
        "messages": history_msgs + [{"role": "user", "content": content}],
    }

    r = requests.post(VISION_API, json=payload, headers=headers, timeout=60)
    if not r.ok:
        return None, f"vision error {r.status_code}: {r.text[:200]}"
    return r.json()["content"][0]["text"].strip(), None

# ── HANDS — execute action ─────────────────────────────────────────────────
def parse_action(response):
    """Extract JSON action block from model response."""
    import re
    m = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL)
    if m:
        try: return json.loads(m.group(1))
        except: pass
    # try bare JSON
    m = re.search(r'\{[^{}]*"action"[^{}]*\}', response, re.DOTALL)
    if m:
        try: return json.loads(m.group(0))
        except: pass
    return None

def execute(action):
    env = {**os.environ, "DISPLAY": DISPLAY}
    act = action.get("action", "")

    if act == "click":
        x, y = action.get("x", 0), action.get("y", 0)
        subprocess.run(["xdotool", "mousemove", str(x), str(y), "click", "1"],
                       env=env, capture_output=True)
        return f"clicked ({x},{y})"

    elif act == "type":
        text = action.get("text", "")
        subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "20", "--", text],
                       env=env, capture_output=True)
        return f"typed: {text[:40]}"

    elif act == "key":
        key = action.get("key", "")
        subprocess.run(["xdotool", "key", key], env=env, capture_output=True)
        return f"pressed: {key}"

    elif act == "scroll":
        x, y = action.get("x", 500), action.get("y", 400)
        btn = "4" if action.get("direction") == "up" else "5"
        for _ in range(3):
            subprocess.run(["xdotool", "click", "--", btn], env=env, capture_output=True)
        return f"scrolled {action.get('direction','down')} at ({x},{y})"

    elif act == "shell":
        cmd = action.get("command", "")
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True,
                               text=True, timeout=15, env=env)
            out = (r.stdout + r.stderr)[:300]
            return f"shell: {cmd}\n→ {out}"
        except Exception as e:
            return f"shell error: {e}"

    elif act == "wait":
        time.sleep(2)
        return "waited"

    elif act == "done":
        return "DONE: " + action.get("reason", "task complete")

    return f"unknown action: {act}"

# ── MAIN LOOP ──────────────────────────────────────────────────────────────
def run(task, observe_only=False, loop_mode=False):
    token = load_token()
    if not token:
        print(f"\n  {RED}no anthropic token — set ~/.anthropic-token{RST}\n")
        sys.exit(1)

    print(f"\n{PINK}{BOLD}  sov-agent{RST}  {GRAY}sovereign computer use{RST}")
    if observe_only:
        print(f"  {GRAY}observe mode — watching only{RST}\n")
    else:
        print(f"  {GOLD}task:{RST}  {task}\n")

    history = []
    steps   = 0

    while steps < MAX_STEPS:
        steps += 1
        print(f"  {CYAN}[step {steps}]{RST}  {GRAY}grabbing screen...{RST}", flush=True)

        img = grab()
        print(f"  {CYAN}[step {steps}]{RST}  {GRAY}thinking...{RST}", flush=True)

        response, err = see_and_decide(img, task, history, token, observe_only)
        if err:
            print(f"  {RED}✗  {err}{RST}")
            break

        # print what the model sees
        print(f"\n  {LIME}◉ sees:{RST}")
        for line in response.split("\n")[:8]:
            print(f"    {GRAY}{line}{RST}")

        if observe_only:
            history.append({"role": "assistant", "content": response})
            history.append({"role": "user",      "content": "continue observing"})
            print()
            if not loop_mode: break
            time.sleep(3)
            continue

        # parse and execute action
        action = parse_action(response)
        if action:
            reason = action.get("reason", "")
            print(f"\n  {GOLD}⚙  {action.get('action','?')}{RST}  {GRAY}{reason}{RST}")
            result = execute(action)
            print(f"  {LIME}↩  {result}{RST}\n")

            history.append({"role": "assistant", "content": response})
            history.append({"role": "user",      "content": f"action result: {result}"})

            if action.get("action") == "done" or result.startswith("DONE"):
                print(f"{LIME}{BOLD}  ✦  task complete{RST}\n")
                break

            time.sleep(1)  # let screen update
        else:
            print(f"  {GRAY}(no action parsed — observing){RST}\n")
            history.append({"role": "assistant", "content": response})
            if not loop_mode: break

    if steps >= MAX_STEPS:
        print(f"  {GRAY}max steps ({MAX_STEPS}) reached{RST}\n")

def main():
    parser = argparse.ArgumentParser(description="sov-agent — sovereign computer use")
    parser.add_argument("task", nargs="?", default="", help="task to perform")
    parser.add_argument("--watch",  action="store_true", help="observe only, no actions")
    parser.add_argument("--loop",   action="store_true", help="keep looping until done")
    parser.add_argument("--steps",  type=int, default=MAX_STEPS)
    args = parser.parse_args()

    global MAX_STEPS
    MAX_STEPS = args.steps

    if not args.task and not args.watch:
        parser.print_help()
        sys.exit(1)

    task = args.task or "observe and describe what is on screen"
    run(task, observe_only=args.watch, loop_mode=args.loop)

if __name__ == "__main__":
    main()
