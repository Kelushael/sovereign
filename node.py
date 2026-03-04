#!/usr/bin/env python3
"""
node.py — universal sovereign mesh daemon
==========================================
One script. Any machine. Any role.

Usage:
  node.py                                  # controller (default)
  node.py --role controller
  node.py --role architect
  node.py --role architect --relay https://axismundi.fun
  node.py --role server
  node.py --role server --model /path/to/model.gguf
  node.py --role relay
  node.py --role all
"""
import os, sys, json, time, socket, threading, itertools, subprocess, argparse
import requests

# ── ANSI ──────────────────────────────────────────────────────────────────────
PINK = "\033[38;2;255;105;180m"
LIME = "\033[38;2;57;255;100m"
CYAN = "\033[38;2;0;220;255m"
GOLD = "\033[38;2;255;200;50m"
GRAY = "\033[38;2;85;85;105m"
RED  = "\033[38;2;255;70;70m"
RST  = "\033[0m"
BOLD = "\033[1m"

# ── CONFIG ────────────────────────────────────────────────────────────────────
RELAY_URL  = "https://axismundi.fun"
MODEL_API  = f"{RELAY_URL}/v1"
MODEL_NAME = "axis-model"
ROOM_GET   = f"{RELAY_URL}/amallo/room"
ROOM_POST  = f"{RELAY_URL}/amallo/room"
REG_URL    = f"{RELAY_URL}/amallo/nodes/register"
HEARTBEAT  = 60          # seconds between heartbeats
POLL_DELAY = 2           # seconds between room polls

HOSTNAME   = socket.gethostname()

# ── TOKEN ─────────────────────────────────────────────────────────────────────
def load_token():
    _cfg = os.path.expanduser("~/.config/axis-mundi")
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

TOKEN = load_token()

def headers():
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# ── SPINNER ───────────────────────────────────────────────────────────────────
class Spin:
    def __init__(self, msg=""):
        self.msg = msg
        self._stop = False
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        for f in itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
            if self._stop: break
            sys.stdout.write(f"\r  {CYAN}{f}{RST}  {self.msg}   ")
            sys.stdout.flush()
            time.sleep(0.1)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *_):
        self._stop = True
        self._t.join()
        sys.stdout.write("\r" + " " * (len(self.msg) + 12) + "\r")
        sys.stdout.flush()

# ── ROOM BUS ──────────────────────────────────────────────────────────────────
def room_post(agent, msg_type, text, target="all"):
    payload = {"agent": agent, "type": msg_type, "text": text, "for": target}
    try:
        r = requests.post(ROOM_POST, json=payload, headers=headers(), timeout=10)
        return r.json() if r.ok else None
    except Exception as e:
        print(f"  {RED}room post error: {e}{RST}")
        return None

def room_get(since=0):
    try:
        r = requests.get(ROOM_GET, params={"since": since}, headers=headers(), timeout=10)
        if r.ok:
            return r.json().get("messages", [])
    except Exception:
        pass
    return []

def node_register(node_id, role, extra=None):
    payload = {"id": node_id, "role": role, "hostname": HOSTNAME}
    if extra:
        payload.update(extra)
    try:
        requests.post(REG_URL, json=payload, headers=headers(), timeout=10)
    except Exception:
        pass

# ── INFERENCE ─────────────────────────────────────────────────────────────────
def infer(prompt, system="You are a helpful assistant."):
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        "stream": False,
    }
    try:
        r = requests.post(f"{MODEL_API}/chat/completions",
                          json=payload, headers=headers(), timeout=120)
        if r.ok:
            return r.json()["choices"][0]["message"]["content"].strip()
        return f"[error {r.status_code}] {r.text[:200]}"
    except Exception as e:
        return f"[inference error] {e}"

# ── CODE HEURISTIC ────────────────────────────────────────────────────────────
CODE_KEYWORDS = (
    "write", "create", "build", "make", "code", "script", "function",
    "class", "implement", "generate", "fix", "debug", "refactor",
    "python", "bash", "javascript", "html", "css", "sql",
)

def looks_like_code_task(text):
    low = text.lower()
    return any(kw in low for kw in CODE_KEYWORDS)

# ── ERROR-DRIVEN CODE LOOP ────────────────────────────────────────────────────
def run_code_loop(task, node_id, max_rounds=5):
    """Generate code, run it, feed errors back, repeat until clean or max rounds."""
    system = (
        "You are a precise code generation agent. "
        "Output ONLY raw executable Python code. No markdown fences, no explanation. "
        "If the task is not Python, output a shell script (#!/usr/bin/env bash). "
        "Fix any errors shown to you on subsequent turns."
    )
    history = [{"role": "system", "content": system},
               {"role": "user",   "content": task}]

    for rnd in range(1, max_rounds + 1):
        print(f"  {GRAY}[architect] round {rnd}/{max_rounds}{RST}")
        try:
            r = requests.post(
                f"{MODEL_API}/chat/completions",
                json={"model": MODEL_NAME, "messages": history, "stream": False},
                headers=headers(), timeout=120,
            )
            if not r.ok:
                return f"[model error {r.status_code}]"
            code = r.json()["choices"][0]["message"]["content"].strip()
            # strip accidental markdown fences
            if code.startswith("```"):
                code = "\n".join(code.split("\n")[1:])
            if code.endswith("```"):
                code = "\n".join(code.split("\n")[:-1])
        except Exception as e:
            return f"[inference error] {e}"

        history.append({"role": "assistant", "content": code})

        # try to run it
        import tempfile
        suffix = ".sh" if code.startswith("#!/usr/bin/env bash") else ".py"
        with tempfile.NamedTemporaryFile(mode="w", suffix=suffix,
                                         delete=False) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        os.chmod(tmp_path, 0o755)
        try:
            result = subprocess.run(
                [sys.executable, tmp_path] if suffix == ".py" else ["bash", tmp_path],
                capture_output=True, text=True, timeout=30,
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
        except subprocess.TimeoutExpired:
            stdout, stderr = "", "execution timed out after 30s"
        finally:
            try: os.unlink(tmp_path)
            except: pass

        if result.returncode == 0:
            print(f"  {LIME}[architect] code ran clean{RST}")
            return f"```\n{code}\n```\n\nOutput:\n{stdout}" if stdout else f"```\n{code}\n```"

        # feed error back
        err_msg = f"Error (returncode {result.returncode}):\n{stderr}"
        if stdout:
            err_msg += f"\nStdout:\n{stdout}"
        print(f"  {GOLD}[architect] error — retrying{RST}")
        history.append({"role": "user", "content": err_msg + "\n\nFix the code."})

    return f"[architect] max rounds reached. Last code:\n```\n{code}\n```"

# ── ROLE: CONTROLLER ──────────────────────────────────────────────────────────
def run_controller(args):
    node_id = f"node-{HOSTNAME}-controller"
    print(f"\n  {PINK}{BOLD}SOVEREIGN MESH{RST}  {GRAY}·{RST}  {CYAN}CONTROLLER{RST}  "
          f"{GRAY}·  {HOSTNAME}{RST}\n")
    print(f"  {GRAY}relay  : {RELAY_URL}{RST}")
    print(f"  {GRAY}model  : {MODEL_API}{RST}")
    print(f"  {GRAY}node   : {node_id}{RST}")
    print(f"  {GRAY}token  : {'set' if TOKEN else 'MISSING'}{RST}\n")
    print(f"  {GOLD}tip:{RST} {GRAY}prefix task with {RST}{CYAN}!{RST}{GRAY} to force route to architect{RST}\n")

    node_register(node_id, "controller")

    # background: poll room for architect results
    result_box = {}
    stop_poll = threading.Event()

    def _poll():
        since = int(time.time())
        while not stop_poll.is_set():
            msgs = room_get(since=since)
            for m in msgs:
                since = max(since, int(m.get("ts", since)) + 1)
                if m.get("type") == "architect_result" and (
                    m.get("for") in ("all", node_id, HOSTNAME)
                ):
                    result_box["latest"] = m.get("text", "")
                    result_box["ts"] = m.get("ts", 0)
            time.sleep(POLL_DELAY)

    poller = threading.Thread(target=_poll, daemon=True)
    poller.start()

    while True:
        try:
            raw = input(f"  {LIME}▸{RST} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {GRAY}bye{RST}\n")
            stop_poll.set()
            break

        if not raw:
            continue
        if raw.lower() in ("/exit", "/quit", "exit", "quit"):
            print(f"\n  {GRAY}bye{RST}\n")
            stop_poll.set()
            break

        force_architect = raw.startswith("!")
        task = raw[1:].strip() if force_architect else raw

        if force_architect or looks_like_code_task(task):
            # route to architect via room bus
            print(f"  {CYAN}→ routing to architect{RST}")
            room_post(node_id, "architect_task", task, target="all")
            # wait for result
            prev_ts = result_box.get("ts", 0)
            waited = 0
            with Spin("waiting for architect"):
                while waited < 120:
                    time.sleep(1)
                    waited += 1
                    if result_box.get("ts", 0) > prev_ts:
                        break
            result = result_box.get("latest", "[no response from architect]")
            print(f"\n  {PINK}architect:{RST}\n{result}\n")
        else:
            # direct inference
            with Spin("thinking"):
                reply = infer(task)
            print(f"\n  {CYAN}axis:{RST} {reply}\n")

# ── ROLE: ARCHITECT ───────────────────────────────────────────────────────────
def run_architect(args):
    node_id = f"node-{HOSTNAME}-architect"
    relay   = args.relay or RELAY_URL
    print(f"\n  {PINK}{BOLD}SOVEREIGN MESH{RST}  {GRAY}·{RST}  {LIME}ARCHITECT{RST}  "
          f"{GRAY}·  {HOSTNAME}{RST}\n")
    print(f"  {GRAY}relay  : {relay}{RST}")
    print(f"  {GRAY}node   : {node_id}{RST}\n")

    # direct task via --task flag
    if args.task:
        print(f"  {GOLD}direct task:{RST} {args.task}\n")
        result = run_code_loop(args.task, node_id)
        print(f"\n  {LIME}result:{RST}\n{result}\n")
        return

    node_register(node_id, "architect")

    # heartbeat thread
    def _heartbeat():
        while True:
            time.sleep(HEARTBEAT)
            node_register(node_id, "architect")
            room_post(node_id, "architect_heartbeat", f"architect alive on {HOSTNAME}")

    threading.Thread(target=_heartbeat, daemon=True).start()

    print(f"  {GRAY}polling room for tasks...{RST}\n")
    since = int(time.time())

    while True:
        try:
            msgs = room_get(since=since)
            for m in msgs:
                since = max(since, int(m.get("ts", since)) + 1)
                if m.get("type") != "architect_task":
                    continue
                target = m.get("for", "all")
                if target not in ("all", node_id, HOSTNAME):
                    continue

                task = m.get("text", "").strip()
                sender = m.get("agent", "unknown")
                if not task:
                    continue

                print(f"  {GOLD}task from {sender}:{RST} {task[:80]}")
                result = run_code_loop(task, node_id)
                room_post(node_id, "architect_result", result, target=sender)
                print(f"  {LIME}result posted to room{RST}\n")

            time.sleep(POLL_DELAY)
        except KeyboardInterrupt:
            print(f"\n  {GRAY}architect stopped{RST}\n")
            break

# ── ROLE: SERVER ──────────────────────────────────────────────────────────────
def find_gguf():
    search_dirs = [
        os.path.expanduser("~/models"),
        os.path.expanduser("~/Downloads"),
        "/root/models",
        "/root/axis-mundi/models",
    ]
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.endswith(".gguf"):
                return os.path.join(d, fn)
    return None

def run_server(args):
    node_id = f"node-{HOSTNAME}-server"
    print(f"\n  {PINK}{BOLD}SOVEREIGN MESH{RST}  {GRAY}·{RST}  {GOLD}SERVER{RST}  "
          f"{GRAY}·  {HOSTNAME}{RST}\n")

    # locate llama-server
    llama_bin = None
    for candidate in ["llama-server", "/usr/local/bin/llama-server"]:
        try:
            subprocess.run([candidate, "--version"],
                           capture_output=True, check=True, timeout=5)
            llama_bin = candidate
            break
        except Exception:
            pass

    if not llama_bin:
        print(f"  {RED}llama-server not found.{RST}\n")
        print(f"  Install via:\n"
              f"    {CYAN}pip install llama-cpp-python{RST}\n"
              f"  or download from:\n"
              f"    {CYAN}https://github.com/ggerganov/llama.cpp/releases{RST}\n")
        return

    # locate model
    model_path = args.model or find_gguf()
    if not model_path:
        print(f"  {RED}no .gguf model found.{RST}\n")
        print(f"  {GRAY}place a .gguf in ~/models/ or pass --model /path/to/model.gguf{RST}\n")
        return

    model_name = os.path.basename(model_path)
    print(f"  {GRAY}model  : {model_name}{RST}")
    print(f"  {GRAY}binary : {llama_bin}{RST}")
    print(f"  {GRAY}port   : 8181{RST}\n")

    node_register(node_id, "server",
                  extra={"model": model_name, "port": 8181})
    room_post(node_id, "server_online",
              f"server online on {HOSTNAME} — model: {model_name} port: 8181")

    def _start_llama():
        cmd = [llama_bin, "-m", model_path,
               "--host", "0.0.0.0", "--port", "8181",
               "--ctx-size", "8192"]
        print(f"  {LIME}starting:{RST} {' '.join(cmd)}\n")
        return subprocess.Popen(cmd)

    proc = _start_llama()

    def _heartbeat():
        while True:
            time.sleep(HEARTBEAT)
            node_register(node_id, "server",
                          extra={"model": model_name, "port": 8181})
            room_post(node_id, "server_heartbeat",
                      f"server alive on {HOSTNAME} — model: {model_name}")

    threading.Thread(target=_heartbeat, daemon=True).start()

    # watch the process, restart if it dies
    print(f"  {GRAY}watching llama-server (PID {proc.pid})...{RST}\n")
    try:
        while True:
            ret = proc.wait()
            print(f"  {RED}llama-server exited (code {ret}) — restarting in 5s{RST}")
            time.sleep(5)
            proc = _start_llama()
    except KeyboardInterrupt:
        print(f"\n  {GRAY}stopping llama-server{RST}")
        proc.terminate()
        print(f"  {GRAY}server stopped{RST}\n")

# ── ROLE: RELAY ───────────────────────────────────────────────────────────────
def run_relay(args):
    node_id = f"node-{HOSTNAME}-relay"
    print(f"\n  {PINK}{BOLD}SOVEREIGN MESH{RST}  {GRAY}·{RST}  {CYAN}RELAY MONITOR{RST}  "
          f"{GRAY}·  {HOSTNAME}{RST}\n")
    print(f"  {GRAY}watching room at {RELAY_URL}{RST}\n")

    node_register(node_id, "relay")

    counts = {}
    since  = int(time.time()) - 60    # show last minute of history

    try:
        while True:
            msgs = room_get(since=since)
            for m in msgs:
                since = max(since, int(m.get("ts", since)) + 1)
                ts    = time.strftime("%H:%M:%S", time.localtime(m.get("ts", 0)))
                agent = m.get("agent", "?")
                mtype = m.get("type", "?")
                target = m.get("for", "all")
                text  = (m.get("text") or "")[:60]
                counts[mtype] = counts.get(mtype, 0) + 1

                color = {
                    "architect_task":      GOLD,
                    "architect_result":    LIME,
                    "architect_heartbeat": GRAY,
                    "server_online":       CYAN,
                    "server_heartbeat":    GRAY,
                    "controller_task":     PINK,
                }.get(mtype, RST)

                print(f"  {GRAY}{ts}{RST}  {color}{mtype:<24}{RST}  "
                      f"{GRAY}from={agent:<22} for={target:<20}{RST}  {text}")

            time.sleep(POLL_DELAY)
    except KeyboardInterrupt:
        print(f"\n  {GRAY}relay stopped{RST}")
        print(f"\n  {GOLD}message counts:{RST}")
        for k, v in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"    {CYAN}{k:<28}{RST} {v}")
        print()

# ── ROLE: ALL ─────────────────────────────────────────────────────────────────
def run_all(args):
    """Run controller + architect on the same machine."""
    arch_args = argparse.Namespace(
        role="architect", relay=None, task=None, model=None
    )
    t = threading.Thread(target=run_architect, args=(arch_args,), daemon=True)
    t.start()
    time.sleep(1)    # let architect register first
    run_controller(args)

# ── MAIN ──────────────────────────────────────────────────────────────────────
ROLE_MAP = {
    "controller": run_controller,
    "architect":  run_architect,
    "server":     run_server,
    "relay":      run_relay,
    "all":        run_all,
}

def main():
    p = argparse.ArgumentParser(
        description="sovereign mesh daemon — one script, any machine, any role"
    )
    p.add_argument("--role",  default="controller",
                   choices=list(ROLE_MAP),
                   help="node role (default: controller)")
    p.add_argument("--model", default=None,
                   help="path to .gguf model (server role)")
    p.add_argument("--relay", default=None,
                   help="relay URL override (architect role)")
    p.add_argument("--task",  default=None,
                   help="run a single task directly (architect role)")
    args = p.parse_args()

    if not TOKEN:
        print(f"  {RED}warning: no auth token found — set ~/.axis-token{RST}\n")

    ROLE_MAP[args.role](args)

if __name__ == "__main__":
    main()
