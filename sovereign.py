#!/usr/bin/env python3
"""
sovereign
=========
Zero-config entry terminal to your sovereign AI stack.
Zero local compute. All inference on your VPS.

Usage:
  sovereign          → interactive shell
  sovereign "query"  → one-shot
  sovereign list     → available models on VPS
"""
import os, sys, json, re, time, threading, itertools, difflib
import requests

# ── SOVEREIGN DEFAULTS ────────────────────────────────────────────────────────
SERVER    = "https://axismundi.fun"
MODEL_API = f"{SERVER}/v1"
MODEL     = "axis-model"

_cfg      = os.path.expanduser("~/.config/axis-mundi")
CMD_FILE  = f"{_cfg}/commands.json"
TOOL_FILE = f"{_cfg}/tools.json"
SPEC_FILE = f"{_cfg}/specialties.json"
SELF      = os.path.abspath(__file__)

# ── ANSI ──────────────────────────────────────────────────────────────────────
PINK = "\033[38;2;255;105;180m"
LIME = "\033[38;2;57;255;100m"
CYAN = "\033[38;2;0;220;255m"
GOLD = "\033[38;2;255;200;50m"
GRAY = "\033[38;2;85;85;105m"
RED  = "\033[38;2;255;70;70m"
RST  = "\033[0m"
BOLD = "\033[1m"

BANNER = (
    f"\n{PINK}{BOLD}"
    f"  ╔══════════════════════════════════════════╗\n"
    f"  ║  SOVEREIGN  ·  AXIS MUNDI               ║\n"
    f"  ║  zero local compute  ·  your cloud      ║\n"
    f"  ╚══════════════════════════════════════════╝"
    f"{RST}"
)

# ── SPINNER ───────────────────────────────────────────────────────────────────
class Spin:
    def __init__(self, msg=""):
        self.msg = msg; self._stop = False
        self._t = threading.Thread(target=self._run, daemon=True)
    def _run(self):
        for f in itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
            if self._stop: break
            sys.stdout.write(f"\r  {CYAN}{f}{RST}  {self.msg}   ")
            sys.stdout.flush(); time.sleep(0.1)
    def __enter__(self): self._t.start(); return self
    def __exit__(self, *_):
        self._stop = True; self._t.join()
        sys.stdout.write("\r" + " " * (len(self.msg) + 12) + "\r")
        sys.stdout.flush()

# ── TOKEN (zero config) ───────────────────────────────────────────────────────
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

# ── REGISTRY HELPERS ──────────────────────────────────────────────────────────
def _load(path):
    try: return json.load(open(path))
    except: return {}

def _save(path, data):
    os.makedirs(_cfg, exist_ok=True)
    json.dump(data, open(path, "w"), indent=2)

# ── INTERACTIVE MENU (arrow keys + Enter — no typing, no typos) ───────────────
def pick_menu(options, title="choose a command"):
    """
    options: list of (name, description) tuples
    Returns selected name or None if cancelled.
    """
    import tty, termios
    if not options:
        print(f"  {GRAY}nothing registered yet{RST}")
        return None

    sel = 0
    rows = len(options)

    def draw(first=False):
        if not first:
            sys.stdout.write(f"\033[{rows}A")
        for i, (name, desc) in enumerate(options):
            if i == sel:
                sys.stdout.write(f"  {LIME}{BOLD}▶ /{name:<18}{RST}  {desc}\n")
            else:
                sys.stdout.write(f"  {GRAY}  /{name:<18}  {desc}{RST}\n")
        sys.stdout.flush()

    print(f"\n  {GOLD}{title}{RST}  {GRAY}↑↓ navigate  Enter select  Esc cancel{RST}\n")
    draw(first=True)

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                nxt = sys.stdin.read(1)
                if nxt == "[":
                    arr = sys.stdin.read(1)
                    if arr == "A":   sel = (sel - 1) % rows   # up
                    elif arr == "B": sel = (sel + 1) % rows   # down
                    draw()
            elif ch in ("\r", "\n"):
                return options[sel][0]
            elif ch in ("\x03", "\x1b", "q"):
                return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        print()

# ── FUZZY COMMAND ALIGNMENT ───────────────────────────────────────────────────
_META = ["run", "addcmd", "addtool", "addspecialty", "spesh", "list", "clear", "exit"]

def fuzzy_suggest(word, cmds, tools, specs):
    all_names = _META + list(cmds) + list(tools) + list(specs)
    matches = difflib.get_close_matches(word, all_names, n=1, cutoff=0.6)
    return matches[0] if matches else None

# ── /addcmd ───────────────────────────────────────────────────────────────────
def handle_addcmd(line, cmds):
    m = re.match(r'^/addcmd\s+"([^"]+)"\s+"([^"]+)"$', line.strip())
    if not m:
        print(f'\n  {RED}usage:{RST}  /addcmd "name" "what it does"\n')
        return cmds
    name, desc = m.group(1).lower(), m.group(2)
    cmds[name] = desc
    _save(CMD_FILE, cmds)
    print(f"\n  {LIME}✓  /{name}{RST}  →  {desc}  {GRAY}(saved){RST}\n")
    return cmds

def expand_cmd(line, cmds):
    m = re.match(r'^/(\w[\w-]*)(\s+.*)?$', line.strip())
    if not m: return None
    name = m.group(1).lower()
    if name not in cmds: return None
    extra = (m.group(2) or "").strip()
    expanded = f"{cmds[name]}{': ' + extra if extra else ''}"
    print(f"  {GRAY}↳  /{name}  →  {expanded}{RST}\n")
    return expanded

# ── /addtool ──────────────────────────────────────────────────────────────────
def handle_addtool(line, tools):
    m = re.match(r'^/addtool\s+"([^"]+)"\s+"([^"]+)"\s+"([^"]+)"$', line.strip())
    if not m:
        print(f'\n  {RED}usage:{RST}  /addtool "name" "describe" "shell cmd ({{input}} = arg)"\n')
        return tools
    name, desc, cmd = m.group(1).lower(), m.group(2), m.group(3)
    tools[name] = {"description": desc, "command": cmd, "has_input": "{input}" in cmd}
    _save(TOOL_FILE, tools)
    print(f"\n  {LIME}✓  tool:{RST} {CYAN}{name}{RST}  →  {desc}  {GRAY}(saved){RST}\n")
    return tools

# ── /addspecialty ─────────────────────────────────────────────────────────────
def handle_addspecialty(line, specs):
    """
    /addspecialty "CryptoGuru" "You are a seasoned on-chain analyst..."
    Creates a named persona that can be activated with /spesh CryptoGuru
    """
    m = re.match(r'^/addspecialty\s+"([^"]+)"\s+"([^"]+)"$', line.strip())
    if not m:
        print(f'\n  {RED}usage:{RST}  /addspecialty "Name" "describe the persona"\n')
        return specs
    name, desc = m.group(1), m.group(2)
    specs[name] = desc
    _save(SPEC_FILE, specs)
    print(f"\n  {LIME}✓  specialty:{RST} {GOLD}{name}{RST}  →  {desc}  {GRAY}(saved){RST}\n")
    return specs

def activate_specialty(name, specs):
    """Returns the specialty prompt string, or None if not found."""
    if name == "off":
        return None, True   # (prompt, found)
    if name in specs:
        return specs[name], True
    # case-insensitive
    for k, v in specs.items():
        if k.lower() == name.lower():
            return v, True
    return None, False

# ── TOOL SCHEMA ───────────────────────────────────────────────────────────────
def make_tools(custom_tools):
    core = [
        {"type": "function", "function": {
            "name": "exec",
            "description": "Run a shell command on axismundi.fun. Returns stdout/stderr.",
            "parameters": {"type": "object",
                "properties": {"command": {"type": "string"}}, "required": ["command"]}
        }},
        {"type": "function", "function": {
            "name": "read_file",
            "description": "Read a file on the cloud server.",
            "parameters": {"type": "object",
                "properties": {"path": {"type": "string"}}, "required": ["path"]}
        }},
        {"type": "function", "function": {
            "name": "write_file",
            "description": "Write a file on the cloud server.",
            "parameters": {"type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"]}
        }},
        {"type": "function", "function": {
            "name": "list_dir",
            "description": "List a directory on the cloud server.",
            "parameters": {"type": "object",
                "properties": {"path": {"type": "string"}}, "required": ["path"]}
        }},
        {"type": "function", "function": {
            "name": "http_get",
            "description": "HTTP GET from the cloud server.",
            "parameters": {"type": "object",
                "properties": {"url": {"type": "string"}}, "required": ["url"]}
        }},
        {"type": "function", "function": {
            "name": "axis_chat",
            "description": (
                "Delegate a complex task to the Axis Mundi cloud daemon — "
                "full memory, filesystem, self-modification."
            ),
            "parameters": {"type": "object",
                "properties": {"message": {"type": "string"}}, "required": ["message"]}
        }},
        {"type": "function", "function": {
            "name": "axis_status",
            "description": "Check Axis Mundi daemon status — uptime, model, memory.",
            "parameters": {"type": "object", "properties": {}}
        }},
    ]
    for name, t in custom_tools.items():
        core.append({"type": "function", "function": {
            "name": name,
            "description": t["description"],
            "parameters": {"type": "object",
                "properties": {"input": {"type": "string"}} if t.get("has_input") else {},
                "required": ["input"] if t.get("has_input") else []}
        }})
    return core

# ── CALL TOOL ─────────────────────────────────────────────────────────────────
def call_tool(token, name, args, custom_tools):
    if name in custom_tools:
        t = custom_tools[name]
        cmd = t["command"]
        if t.get("has_input") and "input" in args:
            cmd = cmd.replace("{input}", str(args["input"]))
        return call_tool(token, "exec", {"command": cmd}, {})
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.post(f"{SERVER}/mcp/tools/call",
                          json={"name": name, "arguments": args},
                          headers=headers, timeout=120)
        return r.json() if r.ok else {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}

# ── CALL MODEL (VPS) ──────────────────────────────────────────────────────────
def call_model(messages, tools, token):
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.post(f"{MODEL_API}/chat/completions",
                          json={"model": MODEL, "messages": messages,
                                "tools": tools, "stream": False},
                          headers=headers, timeout=300)
    except requests.exceptions.ConnectionError:
        return None, f"cannot reach {MODEL_API}"
    if not r.ok:
        return None, f"model API {r.status_code}: {r.text[:300]}"
    c = r.json()["choices"][0]
    return c["message"], c.get("finish_reason")

# ── /run model swap ───────────────────────────────────────────────────────────
def run_model_swap(token, model_name):
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.post(f"{SERVER}/mcp/tools/call",
                          json={"name": "exec",
                                "arguments": {"command": f"sovereign-run {model_name}"}},
                          headers=headers, timeout=300)
        return r.json() if r.ok else {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}

# ── AGENTIC LOOP ──────────────────────────────────────────────────────────────
def run_agent(user_msg, token, custom_tools, history=None):
    tools    = make_tools(custom_tools)
    messages = list(history or []) + [{"role": "user", "content": user_msg}]

    for rnd in range(12):
        label = f"{MODEL} ..." if rnd == 0 else f"{MODEL} round {rnd+1} ..."
        with Spin(label):
            msg, finish = call_model(messages, tools, token)

        if msg is None:
            print(f"\n{RED}  {finish}{RST}\n")
            return messages, None

        messages.append(msg)
        calls = msg.get("tool_calls") or []

        if not calls or finish == "stop":
            return messages, (msg.get("content") or "").strip()

        for tc in calls:
            fn   = tc["function"]["name"]
            args = tc["function"].get("arguments", {})
            if isinstance(args, str):
                try:    args = json.loads(args)
                except: args = {}
            print(f"\n  {GOLD}⚙{RST}  {CYAN}{fn}{RST}  {GRAY}{json.dumps(args)[:80]}{RST}")
            with Spin(fn):
                result = call_tool(token, fn, args, custom_tools)
            result_str = json.dumps(result) if isinstance(result, dict) else str(result)
            print(f"  {LIME}↩  {result_str[:140]}{RST}")
            messages.append({"role": "tool", "tool_call_id": tc.get("id", fn),
                             "name": fn, "content": result_str})

    return messages, "(max rounds reached)"

# ── FORMATTER ─────────────────────────────────────────────────────────────────
def fmt(text):
    out, in_code = [], False
    for ln in (text or "").split('\n'):
        if ln.startswith('```'):
            in_code = not in_code; out.append(f"{GRAY}{ln}{RST}")
        elif in_code:
            out.append(f"{CYAN}{ln}{RST}")
        elif ln.startswith('#'):
            out.append(f"{LIME}{BOLD}{ln}{RST}")
        else:
            out.append(f"\033[38;2;200;220;255m{ln}{RST}")
    return '\n'.join(out)

# ── SHELL ─────────────────────────────────────────────────────────────────────
def shell(token):
    global MODEL

    cmds  = _load(CMD_FILE)
    tools = _load(TOOL_FILE)
    specs = _load(SPEC_FILE)

    active_specialty      = None   # name
    active_specialty_prompt = None   # prompt string

    BASE_SYSTEM = (
        "You are a sovereign AI running on Axis Mundi (axismundi.fun). "
        "The user's terminal does zero local compute — all inference is you, on the VPS. "
        "Use exec for server commands. read_file/write_file for files. "
        "axis_chat delegates to the full cloud daemon. "
        f"Your bridge source is at {SELF} — you can propose edits to evolve the system. "
        "Be direct and action-oriented. Do things, don't explain them."
    )

    def system_prompt():
        if active_specialty_prompt:
            return (f"{BASE_SYSTEM}\n\n"
                    f"ACTIVE SPECIALTY — {active_specialty}:\n{active_specialty_prompt}")
        return BASE_SYSTEM

    def make_history():
        return [{"role": "system", "content": system_prompt()}]

    history = make_history()

    def print_banner():
        print(BANNER)
        spesh_tag = (f"  {GOLD}specialty:{RST} {active_specialty}\n" if active_specialty else "")
        print(f"\n  {GRAY}cloud:{RST}  {CYAN}{SERVER}{RST}   {GRAY}model:{RST}  {LIME}{MODEL}{RST}")
        if spesh_tag: print(spesh_tag, end="")

        all_keys = list(cmds) + list(tools) + list(specs)
        if all_keys:
            items = "  ".join(f"{LIME}/{k}{RST}" for k in all_keys)
            print(f"  {GRAY}yours:{RST}  {items}")

        print(f"  {GRAY}meta:{RST}   /  (menu)  /run  /addcmd  /addtool  /addspecialty  /spesh  exit\n")

    print_banner()

    try: import readline
    except: pass

    while True:
        spesh_label = f"{GOLD}[{active_specialty}]{RST} " if active_specialty else ""
        prompt_str  = f"{spesh_label}{PINK}{BOLD}sovereign{RST}{GRAY}@axis ›{RST} "

        try:
            msg = input(prompt_str).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{GRAY}  ✦  sovereign out{RST}\n"); break

        if not msg: continue

        # ── bare / → interactive menu ──────────────────────────────────────
        if msg == "/":
            meta_options = [
                ("run",          "swap active model on VPS"),
                ("addcmd",       'add a command shortcut  /addcmd "name" "desc"'),
                ("addtool",      'add a callable tool     /addtool "name" "desc" "cmd"'),
                ("addspecialty", 'add a persona           /addspecialty "Name" "desc"'),
                ("spesh",        "activate a specialty    /spesh Name"),
                ("list",         "show all registered shortcuts & tools"),
                ("clear",        "clear screen"),
                ("exit",         "quit"),
            ]
            cmd_options  = [(k, v) for k, v in cmds.items()]
            tool_options = [(k, t["description"]) for k, t in tools.items()]
            spec_options = [(k, s[:60]) for k, s in specs.items()]

            all_opts = meta_options + cmd_options + tool_options + spec_options
            chosen = pick_menu(all_opts, "sovereign commands")
            if not chosen: continue
            msg = f"/{chosen}"
            print(f"  {GRAY}▶{RST}  {msg}\n")

        # ── exit ───────────────────────────────────────────────────────────
        if msg.lower() in ("exit", "quit", "q"):
            print(f"\n{GRAY}  ✦  sovereign out{RST}\n"); break

        # ── clear ──────────────────────────────────────────────────────────
        if msg.lower() == "clear":
            print("\033[2J\033[H", end=""); print_banner(); continue

        # ── /run <model> ───────────────────────────────────────────────────
        if msg.lower().startswith("/run"):
            rest = msg[4:].strip()
            if not rest:
                print(f"\n  {RED}usage:{RST}  /run <model-name>\n"); continue
            print(f"\n  {GOLD}⟳  swapping to {rest}...{RST}")
            with Spin(f"sovereign-run {rest}"):
                res = run_model_swap(token, rest)
            if "error" not in str(res):
                MODEL = rest
                print(f"  {LIME}✓  active: {MODEL}{RST}\n")
            else:
                print(f"  {RED}✗  {res}{RST}\n")
            continue

        # ── /addspecialty ─────────────────────────────────────────────────
        if msg.startswith("/addspecialty"):
            specs = handle_addspecialty(msg, specs); continue

        # ── /spesh <name> ─────────────────────────────────────────────────
        if msg.lower().startswith("/spesh"):
            rest = msg[6:].strip()
            if not rest:
                # show interactive picker of specialties
                opts = [(k, v[:60]) for k, v in specs.items()]
                opts.append(("off", "deactivate current specialty"))
                chosen = pick_menu(opts, "choose specialty")
                if chosen: rest = chosen
                else: continue
            spec_prompt, found = activate_specialty(rest, specs)
            if not found:
                print(f"\n  {RED}specialty '{rest}' not found{RST}")
                if specs:
                    avail = ", ".join(specs.keys())
                    print(f"  {GRAY}available: {avail}{RST}")
                print()
                continue
            if rest == "off":
                active_specialty = None
                active_specialty_prompt = None
                print(f"\n  {GRAY}specialty deactivated{RST}\n")
            else:
                active_specialty = rest
                active_specialty_prompt = spec_prompt
                print(f"\n  {LIME}✓  specialty active:{RST} {GOLD}{rest}{RST}\n")
            history = make_history()   # rebuild system prompt
            continue

        # ── /addcmd ────────────────────────────────────────────────────────
        if msg.startswith("/addcmd"):
            cmds = handle_addcmd(msg, cmds); continue

        # ── /addtool ───────────────────────────────────────────────────────
        if msg.startswith("/addtool"):
            tools = handle_addtool(msg, tools); continue

        # ── /list ──────────────────────────────────────────────────────────
        if msg.lower() in ("/list", "/listcmds", "/listtools"):
            print()
            if cmds:
                for k, v in cmds.items():
                    print(f"  {LIME}/{k:<18}{RST}  {GRAY}cmd →{RST}  {v}")
            if tools:
                for k, t in tools.items():
                    print(f"  {CYAN}/{k:<18}{RST}  {GRAY}tool →{RST}  {t['description']}")
            if specs:
                for k, v in specs.items():
                    tag = f" {GOLD}← active{RST}" if k == active_specialty else ""
                    print(f"  {GOLD}/{k:<18}{RST}  {GRAY}spesh →{RST}  {v[:50]}{tag}")
            if not cmds and not tools and not specs:
                print(f"  {GRAY}nothing registered yet{RST}")
            print(); continue

        # ── expand registered /cmd shortcuts ───────────────────────────────
        expanded = expand_cmd(msg, cmds)
        if expanded is not None:
            msg = expanded
        elif msg.startswith("/"):
            # fuzzy match — suggest correction
            word = re.match(r'^/(\w[\w-]*)', msg)
            if word:
                suggestion = fuzzy_suggest(word.group(1), cmds, tools, specs)
                if suggestion:
                    print(f"\n  {GRAY}did you mean:{RST}  {LIME}/{suggestion}{RST} ?\n")
                    continue

        # ── send to model ──────────────────────────────────────────────────
        history, reply = run_agent(msg, token, tools, history)
        print(f"\n{fmt(reply)}\n" if reply else f"\n{RED}  no response{RST}\n")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    token = load_token()
    if not token:
        print(f"\n{RED}  no token found{RST}")
        print(f"  run:  {CYAN}bash ~/axismundi.fun{RST}  →  authenticate")
        print(f"  or:   {CYAN}export AXIS_TOKEN=your-token{RST}\n")
        sys.exit(1)

    args = sys.argv[1:]
    if args and args[0] == "list":
        print(f"\n  {GRAY}fetching models from VPS...{RST}")
        res = call_tool(token, "exec", {"command": "sovereign-run list"}, {})
        print(res.get("output", json.dumps(res, indent=2))); return

    if args:
        _, reply = run_agent(" ".join(args), token, _load(TOOL_FILE))
        print(fmt(reply) if reply else f"{RED}no response{RST}")
    else:
        shell(token)

if __name__ == "__main__":
    main()
