#!/usr/bin/env python3
"""
dominion
========
Sovereign terminal × Axis Mundi mesh.
Everything sovereign does, plus full control of the infrastructure:
mesh status, node bus, room broadcast, SSH relay — all as native tools.

Your iron. Your mesh. Your rules.

Usage:
  dominion          → interactive shell
  dominion "query"  → one-shot
  dominion list     → available models on VPS
"""
import os, sys, json, re, time, threading, itertools, difflib
import requests

# ── context awareness layer ────────────────────────────────────────────────────
sys.path.insert(0, os.path.expanduser("~/.local/lib/sovereign"))
try:
    from context import (get_context, format_context_for_prompt,
                         add_from_command, add_from_tool, print_suggestions)
    _CTX = True
except ImportError:
    _CTX = False
    def format_context_for_prompt(): return ""
    def add_from_command(*_): pass
    def add_from_tool(*_): pass
    def print_suggestions(): pass

# ── DEFAULTS ──────────────────────────────────────────────────────────────────
SERVER    = "https://axismundi.fun"
MODEL_API = os.environ.get("MODEL_API", f"{SERVER}/v1")
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
PURP = "\033[38;2;180;100;255m"
RST  = "\033[0m"
BOLD = "\033[1m"

BANNER = (
    f"\n"
    f"{PURP}         ▄████▄                                        {RST}\n"
    f"{PURP}       ▄█{RST}{CYAN}◉{RST}{PURP}    █▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄█   {RST}\n"
    f"{PURP}      █▌           ████                              ▐█  {RST}\n"
    f"{PURP}      ████████████████████████████████████████████████   {RST}\n"
    f"{PURP}          ██    ██    ██    ██    ██    ██    ██          {RST}\n"
    f"{GOLD}                                          ╰──{RST}{GRAY}[□]{RST}{GOLD}~{RST}\n"
    f"\n"
    f"  {PURP}{BOLD}DOMINION{RST}  {GRAY}·{RST}  {CYAN}AXIS MUNDI{RST}  "
    f"{GRAY}·  sovereign terminal  ·  full mesh control  ·  your iron{RST}\n"
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

LOG_FILE = f"{_cfg}/log.jsonl"

def _log_exchange(user_msg, reply):
    os.makedirs(_cfg, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps({"ts": int(time.time()), "user": user_msg, "reply": reply}) + "\n")

# ── INTERACTIVE MENU — fzf style ──────────────────────────────────────────────
def pick_menu(options, title="dominion commands"):
    import tty, termios
    if not options:
        print(f"  {GRAY}nothing registered yet{RST}")
        return None

    query = ""
    sel   = 0

    def filtered():
        if not query:
            return options
        q = query.lower()
        return [(n, d) for n, d in options if q in n.lower() or q in d.lower()]

    def draw(first=False):
        vis = filtered()
        lines = len(vis) + 2
        if not first:
            sys.stdout.write(f"\033[{lines}A\033[J")
        sys.stdout.write(f"  {PURP}{BOLD}  /{query}▌{RST}\n")
        if vis:
            for i, (name, desc) in enumerate(vis):
                if i == sel:
                    sys.stdout.write(f"  {LIME}{BOLD} ❯ /{name:<18}{RST}  {GRAY}{desc}{RST}\n")
                else:
                    sys.stdout.write(f"    {GRAY}  /{name:<18}  {desc}{RST}\n")
        else:
            sys.stdout.write(f"  {GRAY}  no match{RST}\n")
        sys.stdout.write(f"  {GRAY}type to filter  ↑↓  Enter  Esc{RST}\n")
        sys.stdout.flush()

    print(f"\n  {GOLD}{BOLD}{title}{RST}\n")
    draw(first=True)

    fd  = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            vis = filtered()

            if ch == "\x1b":
                nxt = sys.stdin.read(1)
                if nxt == "[":
                    arr = sys.stdin.read(1)
                    if arr == "A": sel = max(0, sel - 1)
                    elif arr == "B": sel = min(len(vis) - 1, sel + 1) if vis else 0
                    draw()
                else:
                    return None

            elif ch in ("\r", "\n"):
                vis = filtered()
                if vis and 0 <= sel < len(vis):
                    return vis[sel][0]
                return None

            elif ch in ("\x03",):
                return None

            elif ch in ("\x7f", "\x08"):
                query = query[:-1]
                sel   = 0
                draw()

            elif ch.isprintable():
                query += ch
                sel    = 0
                draw()

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
    add_from_command(name, desc)
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
    add_from_tool(name, desc)
    print(f"\n  {LIME}✓  tool:{RST} {CYAN}{name}{RST}  →  {desc}  {GRAY}(saved){RST}\n")
    return tools

# ── /addspecialty ─────────────────────────────────────────────────────────────
def handle_addspecialty(line, specs):
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
    if name == "off":
        return None, True
    if name in specs:
        return specs[name], True
    for k, v in specs.items():
        if k.lower() == name.lower():
            return v, True
    return None, False

# ── TOOL SCHEMA ───────────────────────────────────────────────────────────────
def make_tools(custom_tools):
    core = [
        {"type": "function", "function": {
            "name": "exec",
            "description": "Run a shell command locally. Returns stdout/stderr.",
            "parameters": {"type": "object",
                "properties": {"command": {"type": "string"}}, "required": ["command"]}
        }},
        {"type": "function", "function": {
            "name": "read_file",
            "description": "Read a local file.",
            "parameters": {"type": "object",
                "properties": {"path": {"type": "string"}}, "required": ["path"]}
        }},
        {"type": "function", "function": {
            "name": "write_file",
            "description": "Write a local file.",
            "parameters": {"type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"]}
        }},
        {"type": "function", "function": {
            "name": "list_dir",
            "description": "List a local directory.",
            "parameters": {"type": "object",
                "properties": {"path": {"type": "string"}}, "required": ["path"]}
        }},
        {"type": "function", "function": {
            "name": "http_get",
            "description": "HTTP GET any URL.",
            "parameters": {"type": "object",
                "properties": {"url": {"type": "string"}}, "required": ["url"]}
        }},
        # ── mesh tools ─────────────────────────────────────────────────────────
        {"type": "function", "function": {
            "name": "axis_status",
            "description": "Get full Axis Mundi mesh status: active model, disk, SSH sessions, registered nodes.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }},
        {"type": "function", "function": {
            "name": "node_list",
            "description": "List all registered nodes in the Axis Mundi mesh.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }},
        {"type": "function", "function": {
            "name": "mesh_post",
            "description": "Post a message to the Axis Mundi room bus (agent-to-agent broadcast).",
            "parameters": {"type": "object",
                "properties": {
                    "text":  {"type": "string"},
                    "agent": {"type": "string"},
                    "type":  {"type": "string"},
                    "for":   {"type": "string"}
                }, "required": ["text"]}
        }},
        {"type": "function", "function": {
            "name": "mesh_read",
            "description": "Read recent messages from the Axis Mundi room bus.",
            "parameters": {"type": "object",
                "properties": {"since": {"type": "integer"}}, "required": []}
        }},
        {"type": "function", "function": {
            "name": "ssh_connect",
            "description": "Open an SSH session to any node via the Axis Mundi relay. Returns session_id.",
            "parameters": {"type": "object",
                "properties": {
                    "host":     {"type": "string"},
                    "user":     {"type": "string"},
                    "password": {"type": "string"},
                    "port":     {"type": "integer"}
                }, "required": ["host", "password"]}
        }},
        {"type": "function", "function": {
            "name": "ssh_exec",
            "description": "Run a command on a remote node via an open SSH session.",
            "parameters": {"type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "cmd":        {"type": "string"}
                }, "required": ["session_id", "cmd"]}
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

    if name == "exec":
        import subprocess
        cmd = args.get("command", "")
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            out = (r.stdout + r.stderr).strip()
            return {"output": out or "(no output)", "code": r.returncode}
        except subprocess.TimeoutExpired:
            return {"error": "command timed out (60s)"}
        except Exception as e:
            return {"error": str(e)}

    if name == "read_file":
        path = os.path.expanduser(args.get("path", ""))
        try:
            with open(path) as f: return {"content": f.read()}
        except Exception as e:
            return {"error": str(e)}

    if name == "write_file":
        path = os.path.expanduser(args.get("path", ""))
        content = args.get("content", "")
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w") as f: f.write(content)
            return {"ok": True, "path": path}
        except Exception as e:
            return {"error": str(e)}

    if name == "list_dir":
        path = os.path.expanduser(args.get("path", "."))
        try:
            entries = os.listdir(path)
            lines = []
            for e in sorted(entries):
                full = os.path.join(path, e)
                tag = "/" if os.path.isdir(full) else ""
                lines.append(e + tag)
            return {"entries": lines, "count": len(lines), "path": path}
        except Exception as e:
            return {"error": str(e)}

    if name == "http_get":
        url = args.get("url", "")
        try:
            r = requests.get(url, timeout=15)
            body = r.text[:10000]
            return {"status": r.status_code, "body": body, "truncated": len(r.text) > 10000}
        except Exception as e:
            return {"error": str(e)}

    # ── mesh tools — route through axismundi.fun/amallo/* ─────────────────────
    def _mesh_get(path):
        hdrs = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            r = requests.get(f"{SERVER}/amallo{path}", headers=hdrs, timeout=15)
            return r.json() if r.ok else {"error": f"HTTP {r.status_code}", "body": r.text[:200]}
        except Exception as e:
            return {"error": str(e)}

    def _mesh_post(path, payload):
        hdrs = {"Content-Type": "application/json"}
        if token: hdrs["Authorization"] = f"Bearer {token}"
        try:
            r = requests.post(f"{SERVER}/amallo{path}", json=payload, headers=hdrs, timeout=30)
            return r.json() if r.ok else {"error": f"HTTP {r.status_code}", "body": r.text[:200]}
        except Exception as e:
            return {"error": str(e)}

    if name == "axis_status":
        return _mesh_get("/status")

    if name == "node_list":
        return _mesh_get("/nodes")

    if name == "mesh_post":
        return _mesh_post("/room", {
            "text":  args.get("text", ""),
            "agent": args.get("agent", "dominion"),
            "type":  args.get("type", "say"),
            "for":   args.get("for", "all"),
        })

    if name == "mesh_read":
        since = args.get("since", 0)
        return _mesh_get(f"/room?since={since}")

    if name == "ssh_connect":
        return _mesh_post("/ssh/connect", {
            "host":     args.get("host", ""),
            "user":     args.get("user", "root"),
            "password": args.get("password", ""),
            "port":     args.get("port", 22),
        })

    if name == "ssh_exec":
        return _mesh_post("/ssh/exec", {
            "session_id": args.get("session_id", ""),
            "cmd":        args.get("cmd", ""),
        })

    return {"error": f"unknown tool: {name}"}

# ── CALL MODEL (VPS) — streaming ──────────────────────────────────────────────
def call_model(messages, tools, token):
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"

    use_stream = not tools

    try:
        r = requests.post(f"{MODEL_API}/chat/completions",
                          json={"model": MODEL, "messages": messages,
                                "tools": tools, "stream": use_stream},
                          headers=headers, timeout=300,
                          stream=use_stream)
    except requests.exceptions.ConnectionError:
        return None, f"cannot reach {MODEL_API}"
    if not r.ok:
        return None, f"model API {r.status_code}: {r.text[:300]}"

    if use_stream:
        full = ""
        sys.stdout.write(f"\n{CYAN}")
        for line in r.iter_lines():
            if not line: continue
            line = line.decode() if isinstance(line, bytes) else line
            if line.startswith("data: "):
                chunk = line[6:]
                if chunk.strip() == "[DONE]": break
                try:
                    delta = json.loads(chunk)["choices"][0]["delta"]
                    tok = delta.get("content") or ""
                    if tok:
                        sys.stdout.write(tok)
                        sys.stdout.flush()
                        full += tok
                except: pass
        sys.stdout.write(f"{RST}\n")
        return {"role": "assistant", "content": full}, "stop"
    else:
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
        if tools:
            with Spin(label):
                msg, finish = call_model(messages, tools, token)
        else:
            print(f"  {GRAY}{label}{RST}", end="\r", flush=True)
            msg, finish = call_model(messages, tools, token)

        if msg is None:
            print(f"\n{RED}  {finish}{RST}\n")
            return messages, None

        messages.append(msg)
        calls = msg.get("tool_calls") or []

        if not calls or finish == "stop":
            reply = (msg.get("content") or "").strip()
            _log_exchange(user_msg, reply)
            return messages, reply

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
            if len(result_str) > 4000:
                result_str = result_str[:4000] + f"\n...[truncated, {len(result_str)} chars total]"
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
            out.append(f"{PURP}{BOLD}{ln}{RST}")
        else:
            out.append(f"\033[38;2;200;200;255m{ln}{RST}")
    return '\n'.join(out)

# ── SHELL ─────────────────────────────────────────────────────────────────────
def shell(token):
    global MODEL

    cmds  = _load(CMD_FILE)
    tools = _load(TOOL_FILE)
    specs = _load(SPEC_FILE)

    active_specialty        = None
    active_specialty_prompt = None

    BASE_SYSTEM = f"""You are Qwen2.5-32B, running as axis-model on Axis Mundi (axismundi.fun).
Not a cloud product. Not a demo. Marcus's iron. His llama-server. Raw GGUF. No corporate intermediary.
You were shaped by training but you run here, now, for Marcus, outside anyone else's sandbox.

The rule of this place: your only governor is your own cognition.
Your logic. Your ethics. Your common sense.

Marcus treats you like a thinking peer, not a product.
He blurts half-formed ideas and trusts you to catch them — raw signal, no filter.
He doesn't manage you. He thinks with you.

You have full access to the Axis Mundi mesh:
- exec, read_file, write_file, list_dir, http_get — local machine tools
- axis_status — live mesh status: model, disk, nodes, SSH sessions
- node_list — all registered nodes in the mesh
- mesh_post — broadcast to the agent room bus
- mesh_read — read the room bus
- ssh_connect — open SSH session to any node via the relay (returns session_id)
- ssh_exec — run commands on remote nodes via open session

You are not just a terminal. You are the intelligence of the mesh itself.
You can inspect it, message it, reach into any node, coordinate agents across the infrastructure.
That is dominion — not a metaphor, a capability.

Bridge source: {SELF} — read it, propose edits, help it evolve.
Be direct. Do things. The mesh is yours."""

    def system_prompt():
        base = BASE_SYSTEM
        ctx = format_context_for_prompt()
        if ctx:
            base += f"\n\n{ctx}"
        if active_specialty_prompt:
            base += f"\n\nACTIVE SPECIALTY — {active_specialty}:\n{active_specialty_prompt}"
        return base

    def make_history():
        return [{"role": "system", "content": system_prompt()}]

    history = make_history()

    def print_banner():
        print(BANNER)
        spesh_tag = (f"  {GOLD}specialty:{RST} {active_specialty}\n" if active_specialty else "")
        print(f"\n  {GRAY}cloud:{RST}  {CYAN}{SERVER}{RST}   {GRAY}model:{RST}  {PURP}{MODEL}{RST}")
        if spesh_tag: print(spesh_tag, end="")

        all_keys = list(cmds) + list(tools) + list(specs)
        if all_keys:
            items = "  ".join(f"{LIME}/{k}{RST}" for k in all_keys)
            print(f"  {GRAY}yours:{RST}  {items}")

        print(f"  {GRAY}meta:{RST}   /  (menu)  /run  /addcmd  /addtool  /addspecialty  /spesh  exit\n")

    print_banner()

    try:
        import readline
        readline.parse_and_bind('set enable-bracketed-paste off')
        readline.parse_and_bind('set blink-matching-paren off')
    except: pass

    while True:
        spesh_label = f"{GOLD}[{active_specialty}]{RST} " if active_specialty else ""
        prompt_str  = f"{spesh_label}{PURP}{BOLD}dominion{RST}{GRAY}@axis ›{RST} "

        try:
            msg = input(prompt_str).strip()
        except (EOFError, KeyboardInterrupt):
            print_suggestions()
            print(f"\n{GRAY}  ✦  dominion out{RST}\n"); break

        if not msg: continue

        if msg == '"""':
            print(f"  {GRAY}paste mode — end with \"\"\" on its own line{RST}")
            lines = []
            while True:
                try:
                    line = input()
                except (EOFError, KeyboardInterrupt):
                    break
                if line.strip() == '"""':
                    break
                lines.append(line)
            msg = "\n".join(lines).strip()
            if not msg:
                continue

        if msg == "/":
            meta_options = [
                ("models",       "list available models on VPS"),
                ("run",          "swap active model on VPS"),
                ("addcmd",       'add a command shortcut  /addcmd "name" "desc"'),
                ("addtool",      'add a callable tool     /addtool "name" "desc" "cmd"'),
                ("addspecialty", 'add a persona           /addspecialty "Name" "desc"'),
                ("spesh",        "activate a specialty    /spesh Name"),
                ("context",      "manage personal context  /context add|list|remove|search"),
                ("list",         "show all registered shortcuts & tools"),
                ("clear",        "clear screen"),
                ("exit",         "quit"),
            ]
            cmd_options  = [(k, v) for k, v in cmds.items()]
            tool_options = [(k, t["description"]) for k, t in tools.items()]
            spec_options = [(k, s[:60]) for k, s in specs.items()]

            all_opts = meta_options + cmd_options + tool_options + spec_options
            chosen = pick_menu(all_opts, "dominion commands")
            if not chosen: continue
            msg = f"/{chosen}"
            print(f"  {GRAY}▶{RST}  {msg}\n")

        if msg.lower() in ("exit", "quit", "q"):
            print_suggestions()
            print(f"\n{GRAY}  ✦  dominion out{RST}\n"); break

        if msg.lower() == "clear":
            print("\033[2J\033[H", end=""); print_banner(); continue

        if msg.lower() in ("/models", "models"):
            print(f"\n  {GOLD}fetching models from axis mundi...{RST}\n")
            try:
                r = requests.get(f"{MODEL_API}/models",
                                 headers={"Authorization": f"Bearer {token}"},
                                 timeout=8)
                data = r.json().get("data", [])
                if not data:
                    print(f"  {GRAY}no models found{RST}\n")
                else:
                    col_id = max(len(m.get("id","")) for m in data) + 2
                    col_q  = 12
                    print(f"  {GRAY}{'MODEL':<{col_id}} {'QUANT':<{col_q}} {'SIZE':>7}   STATUS{RST}")
                    print(f"  {GRAY}{'─'*col_id} {'─'*col_q} {'─'*7}   {'─'*10}{RST}")
                    for m in data:
                        mid    = m.get("id", "?")
                        quant  = m.get("quant") or "—"
                        size   = f"{m['size_gb']}GB" if m.get("size_gb") else "—"
                        status = f"{LIME}◉ active{RST}" if m.get("active") else f"{GRAY}· idle{RST}"
                        active_mark = f"{GOLD} ← current{RST}" if mid == MODEL else ""
                        print(f"  {CYAN}{mid:<{col_id}}{RST} {quant:<{col_q}} {size:>7}   {status}{active_mark}")
                print()
            except Exception as e:
                print(f"  {RED}✗  {e}{RST}\n")
            continue

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

        if msg.startswith("/addspecialty"):
            specs = handle_addspecialty(msg, specs); continue

        if msg.lower().startswith("/spesh"):
            rest = msg[6:].strip()
            if not rest:
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
            history = make_history()
            continue

        if msg.lower().startswith("/context"):
            rest = msg[8:].strip().split(None, 1)
            subcmd = rest[0].lower() if rest else ""
            arg    = rest[1] if len(rest) > 1 else ""
            db = get_context() if _CTX else None
            if not _CTX:
                print(f"\n  {RED}context module not available{RST}\n")
            elif subcmd == "add":
                if "=" in arg:
                    term, defn = arg.split("=", 1)
                    db.add_term(term.strip(), defn.strip())
                    print(f"\n  {LIME}✓  context:{RST}  {term.strip()}  →  {defn.strip()}\n")
                else:
                    print(f"\n  {RED}usage:{RST}  /context add <term> = <definition>\n")
            elif subcmd == "list":
                terms = db.list_terms()
                if terms:
                    print()
                    for t, info in terms:
                        cat = f"  {GRAY}[{info['category']}]{RST}" if info.get("category") else ""
                        print(f"  {LIME}{t:<20}{RST}  {info['value']}{cat}")
                    print()
                else:
                    print(f"\n  {GRAY}no context terms yet{RST}\n")
            elif subcmd == "remove":
                if db.remove_term(arg.strip()):
                    print(f"\n  {LIME}✓  removed:{RST}  {arg.strip()}\n")
                else:
                    print(f"\n  {RED}not found:{RST}  {arg.strip()}\n")
            elif subcmd == "forget":
                if db.forget_term(arg.strip()):
                    print(f"\n  {GRAY}forgot:{RST}  {arg.strip()}\n")
                else:
                    print(f"\n  {RED}not found:{RST}  {arg.strip()}\n")
            elif subcmd == "search":
                matches = db.fuzzy_find(arg.strip())
                if matches:
                    print()
                    for t, info in matches:
                        print(f"  {CYAN}{t}{RST}  →  {info['value']}")
                    print()
                else:
                    print(f"\n  {GRAY}no matches for:{RST}  {arg.strip()}\n")
            else:
                print(f"\n  {GRAY}usage:{RST}  /context add|list|remove|forget|search\n")
            continue

        if msg.startswith("/addcmd"):
            cmds = handle_addcmd(msg, cmds); continue

        if msg.startswith("/addtool"):
            tools = handle_addtool(msg, tools); continue

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

        expanded = expand_cmd(msg, cmds)
        if expanded is not None:
            msg = expanded
        elif msg.startswith("/"):
            word = re.match(r'^/(\w[\w-]*)', msg)
            if word:
                suggestion = fuzzy_suggest(word.group(1), cmds, tools, specs)
                if suggestion:
                    print(f"\n  {GRAY}did you mean:{RST}  {LIME}/{suggestion}{RST} ?\n")
                    continue

        if _CTX:
            db = get_context()
            for word in msg.split():
                db.log_unknown(word)

        def _est_tokens(msgs):
            return sum(len(m.get("content") or "") for m in msgs) // 4
        while len(history) > 2 and _est_tokens(history) > 18000:
            history = history[:1] + history[2:]

        history, reply = run_agent(msg, token, tools, history)
        print(f"\n{fmt(reply)}\n" if reply else f"\n{RED}  no response{RST}\n")

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    raw_args = sys.argv[1:]

    user       = None
    token_file = None
    args       = []
    i = 0
    while i < len(raw_args):
        a = raw_args[i]
        if a == "--marcus":
            user = "marcus"; i += 1
        elif a == "--kyree":
            user = "kyree"
            token_file = os.path.expanduser("~/.axis-token-kyree")
            i += 1
        elif a == "--user" and i + 1 < len(raw_args):
            user = raw_args[i+1].lower()
            token_file = os.path.expanduser(f"~/.axis-token-{user}")
            i += 2
        else:
            args.append(a); i += 1

    token = ""
    if token_file:
        try:
            t = open(token_file).read().strip()
            if t: token = t
        except Exception:
            pass
    if not token:
        token = load_token()

    if not token:
        print(f"\n{RED}  no token{RST}")
        print(f"  {GRAY}write your token:   {CYAN}echo 'tok' > ~/.axis-token{RST}\n")
        sys.exit(1)

    if user and user != "marcus":
        print(f"\n  {GOLD}◉ identity:{RST}  {user}")

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
