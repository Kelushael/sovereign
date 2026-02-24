#!/usr/bin/env python3
"""
cherub — sovereign pattern watcher
====================================
Reads your recent sovereign conversations.
Asks the model what patterns it sees.
Proposes /addcmd entries one at a time.
You approve. Shell gets smarter.

Usage:
  cherub          → analyze last 20 exchanges
  cherub 40       → analyze last 40 exchanges
"""
import os, sys, json, time
import requests

# ── same defaults as sovereign ────────────────────────────────────────────────
SERVER    = "https://axismundi.fun"
MODEL_API = f"{SERVER}/v1"
MODEL     = "axis-model"

_cfg      = os.path.expanduser("~/.config/axis-mundi")
LOG_FILE  = f"{_cfg}/log.jsonl"
CMD_FILE  = f"{_cfg}/commands.json"

# ── ANSI ──────────────────────────────────────────────────────────────────────
PINK = "\033[38;2;255;105;180m"
LIME = "\033[38;2;57;255;100m"
CYAN = "\033[38;2;0;220;255m"
GOLD = "\033[38;2;255;200;50m"
GRAY = "\033[38;2;85;85;105m"
RED  = "\033[38;2;255;70;70m"
RST  = "\033[0m"
BOLD = "\033[1m"

# ── TOKEN ─────────────────────────────────────────────────────────────────────
def load_token():
    for src in [
        lambda: open(os.path.expanduser("~/.axis-token")).read().strip(),
        lambda: json.load(open(f"{_cfg}/config.json")).get("token", ""),
        lambda: os.environ.get("AXIS_TOKEN", ""),
    ]:
        try:
            t = src()
            if t: return t
        except Exception:
            pass
    return ""

# ── READ LOG ──────────────────────────────────────────────────────────────────
def read_log(n=20):
    if not os.path.exists(LOG_FILE):
        return []
    lines = open(LOG_FILE).readlines()
    entries = []
    for ln in lines[-n:]:
        try: entries.append(json.loads(ln.strip()))
        except: pass
    return entries

# ── ASK MODEL ────────────────────────────────────────────────────────────────
def ask_model(exchanges, token):
    convo = "\n".join(
        f"USER: {e['user']}\nASSISTANT: {e['reply'][:200]}"
        for e in exchanges
    )

    prompt = (
        "Below are recent conversations from a sovereign terminal session.\n\n"
        f"{convo}\n\n"
        "Identify recurring intents, patterns, or tasks the user keeps doing.\n"
        "Suggest 3 to 5 useful /addcmd shortcuts they should have.\n"
        "Reply ONLY in this exact format, one per line, nothing else:\n"
        "NAME | what this command tells the AI to do\n\n"
        "Rules:\n"
        "- NAME must be one word, lowercase, no spaces\n"
        "- Only suggest things you actually saw in the conversations\n"
        "- Be specific, not generic\n"
        "- Do not explain, just list"
    )

    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"

    try:
        r = requests.post(
            f"{MODEL_API}/chat/completions",
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            headers=headers,
            timeout=120,
        )
    except requests.exceptions.ConnectionError:
        print(f"\n{RED}  cannot reach {MODEL_API}{RST}\n")
        return []

    if not r.ok:
        print(f"\n{RED}  model error {r.status_code}{RST}\n")
        return []

    content = r.json()["choices"][0]["message"].get("content", "").strip()
    return parse_suggestions(content)

# ── PARSE SUGGESTIONS ─────────────────────────────────────────────────────────
def parse_suggestions(text):
    suggestions = []
    for line in text.splitlines():
        line = line.strip()
        if "|" not in line: continue
        parts = line.split("|", 1)
        if len(parts) != 2: continue
        name = parts[0].strip().lower().replace(" ", "-").replace("/", "")
        desc = parts[1].strip()
        if name and desc:
            suggestions.append((name, desc))
    return suggestions

# ── APPROVE LOOP ──────────────────────────────────────────────────────────────
def approve(suggestions, token):
    if not suggestions:
        print(f"\n  {GRAY}no patterns found — have a few more conversations first{RST}\n")
        return

    cmds = {}
    try: cmds = json.load(open(CMD_FILE))
    except: pass

    added = 0
    print(f"\n  {GOLD}cherub found {len(suggestions)} pattern(s):{RST}\n")

    for name, desc in suggestions:
        already = f"  {GRAY}(already registered){RST}" if name in cmds else ""
        print(f"  {LIME}/{name}{RST}  →  {desc}{already}")

        if name in cmds:
            print(f"  {GRAY}skipping — already exists{RST}\n")
            continue

        try:
            ans = input(f"  {CYAN}add?{RST} {GRAY}[y/n/q]:{RST} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(); break

        if ans == "q":
            break
        elif ans == "y":
            cmds[name] = desc
            os.makedirs(_cfg, exist_ok=True)
            json.dump(cmds, open(CMD_FILE, "w"), indent=2)
            print(f"  {LIME}✓ saved{RST}\n")
            added += 1
        else:
            print(f"  {GRAY}skipped{RST}\n")

    if added:
        print(f"  {LIME}✓  {added} command(s) added — run sovereign and type / to see them{RST}\n")
    else:
        print(f"  {GRAY}nothing added{RST}\n")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 20

    print(f"\n{PINK}{BOLD}  cherub{RST}  {GRAY}— sovereign pattern watcher{RST}\n")

    token = load_token()
    if not token:
        print(f"{RED}  no token — run bash ~/axismundi.fun first{RST}\n")
        sys.exit(1)

    exchanges = read_log(n)
    if not exchanges:
        print(f"  {GRAY}no conversations logged yet — use sovereign first{RST}\n")
        return

    print(f"  {GRAY}reading last {len(exchanges)} exchanges...{RST}")
    print(f"  {GRAY}asking model for patterns...{RST}\n")

    suggestions = ask_model(exchanges, token)
    approve(suggestions, token)

if __name__ == "__main__":
    main()
