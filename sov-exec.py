#!/usr/bin/env python3
"""
sov-exec
========
Error-driven code execution agent for the sovereign mesh.
Writes code, runs it, feeds errors back to the model, loops until success.

Usage:
  sov-exec "download all images from https://example.com"
  sov-exec
  sov-exec --max 12 "build a flask server"
"""
import os, sys, re, json, time, threading, itertools, subprocess, tempfile
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
MODEL_API    = os.environ.get("MODEL_API", "https://axismundi.fun/v1")
MODEL        = "axis-model"
_cfg         = os.path.expanduser("~/.config/axis-mundi")
EXEC_DIR     = f"{_cfg}/execs"
DEFAULT_MAX  = 8

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

# ── MODEL CALL ────────────────────────────────────────────────────────────────
def call_model(messages, token):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.post(
            f"{MODEL_API}/chat/completions",
            json={"model": MODEL, "messages": messages, "stream": False},
            headers=headers,
            timeout=300,
        )
    except requests.exceptions.ConnectionError:
        return None, f"cannot reach {MODEL_API}"
    if not r.ok:
        return None, f"model API {r.status_code}: {r.text[:300]}"
    c = r.json()["choices"][0]
    return c["message"]["content"], c.get("finish_reason")

# ── CODE EXTRACTION ───────────────────────────────────────────────────────────
def extract_code(text):
    """Pull code from a ```python ... ``` or ``` ... ``` block, or return raw."""
    # try fenced python block first
    m = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # plain fenced block
    m = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # no fences — assume the whole response is code
    return text.strip()

# ── BUILD PROMPT ──────────────────────────────────────────────────────────────
def build_prompt(task, prev_code=None, error=None):
    if prev_code is None:
        return (
            f"Write Python code to accomplish this task:\n\n{task}\n\n"
            "Return ONLY the code block. No explanation. No markdown prose. "
            "Just the raw Python code inside a single ```python ... ``` block."
        )
    snippet = error[-300:] if error else "(unknown error)"
    return (
        f"Task: {task}\n\n"
        f"Previous code attempt:\n```python\n{prev_code}\n```\n\n"
        f"Error output (last 300 chars):\n{snippet}\n\n"
        "Fix the code. Return ONLY the fixed Python code block, no explanation."
    )

# ── RUN CODE ──────────────────────────────────────────────────────────────────
def run_code(code):
    """Write code to a temp file, execute it, return (returncode, stdout+stderr)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, prefix="sovexec_"
    ) as f:
        f.write(code)
        tmp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode, output, tmp_path
    except subprocess.TimeoutExpired:
        return 1, "execution timed out (60s)", tmp_path
    except Exception as e:
        return 1, str(e), tmp_path

# ── SAVE SUCCESSFUL CODE ──────────────────────────────────────────────────────
def save_exec(code, task):
    os.makedirs(EXEC_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "_", task.lower())[:40].strip("_")
    path = f"{EXEC_DIR}/{ts}_{slug}.py"
    with open(path, "w") as f:
        f.write(f"# task: {task}\n# saved by sov-exec\n\n{code}\n")
    return path

# ── SHOW CODE PREVIEW ─────────────────────────────────────────────────────────
def show_code(code, iteration, max_iter):
    lines = code.split("\n")
    preview_lines = lines[:20]
    truncated = len(lines) > 20
    print(f"\n  {GOLD}{BOLD}iteration {iteration}/{max_iter}{RST}  {GRAY}— generated code:{RST}\n")
    for ln in preview_lines:
        print(f"  {CYAN}{ln}{RST}")
    if truncated:
        print(f"  {GRAY}... (+{len(lines) - 20} more lines){RST}")
    print()

# ── EDIT IN EDITOR ────────────────────────────────────────────────────────────
def edit_in_editor(code):
    editor = os.environ.get("EDITOR", "nano")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, prefix="sovexec_edit_"
    ) as f:
        f.write(code)
        tmp = f.name
    subprocess.run([editor, tmp])
    try:
        with open(tmp) as f:
            edited = f.read()
        os.unlink(tmp)
        return edited.strip()
    except Exception:
        return code

# ── MAIN EXEC LOOP ────────────────────────────────────────────────────────────
def sov_exec(task, max_iter, token):
    print(f"\n  {PINK}{BOLD}sov-exec{RST}  {GRAY}·{RST}  {CYAN}{task[:80]}{RST}\n")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a Python code generation agent. "
                "When given a task, return ONLY the Python code in a single "
                "```python ... ``` block. No explanations, no prose, no comments "
                "outside the block. The code must be complete and runnable as-is."
            ),
        }
    ]

    prev_code = None
    error_out = None

    for iteration in range(1, max_iter + 1):
        # ── ask the model ──────────────────────────────────────────────────
        prompt = build_prompt(task, prev_code, error_out)
        messages.append({"role": "user", "content": prompt})

        spin_label = f"generating code  (iter {iteration}/{max_iter})"
        with Spin(spin_label):
            reply, _ = call_model(messages, token)

        if reply is None:
            print(f"\n  {RED}✗  model error: {_}{RST}\n")
            return False

        messages.append({"role": "assistant", "content": reply})

        code = extract_code(reply)
        if not code:
            print(f"\n  {RED}✗  no code in model response{RST}\n")
            return False

        show_code(code, iteration, max_iter)

        # ── first iteration: ask user before running ───────────────────────
        if iteration == 1:
            while True:
                try:
                    ans = input(
                        f"  {GOLD}run this?{RST}  {GRAY}[y/n/e(edit)]{RST}  "
                    ).strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print(f"\n  {GRAY}aborted{RST}\n")
                    return False

                if ans in ("y", "yes", ""):
                    break
                elif ans in ("n", "no"):
                    print(f"\n  {GRAY}cancelled{RST}\n")
                    return False
                elif ans in ("e", "edit"):
                    code = edit_in_editor(code)
                    print(f"\n  {GRAY}using edited code{RST}\n")
                    break
                else:
                    print(f"  {GRAY}y / n / e{RST}")

        # ── run the code ───────────────────────────────────────────────────
        print(f"  {GRAY}running...{RST}", end="\r", flush=True)
        returncode, output, tmp_path = run_code(code)

        # clean up temp file
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        if returncode == 0:
            print(f"  {LIME}✓  success  (iter {iteration}/{max_iter}){RST}")
            if output:
                print(f"\n  {GRAY}output:{RST}\n")
                for line in output.split("\n")[:30]:
                    print(f"  {CYAN}{line}{RST}")
                if len(output.split("\n")) > 30:
                    print(f"  {GRAY}... (truncated){RST}")
            saved = save_exec(code, task)
            print(f"\n  {GOLD}saved:{RST}  {saved}\n")
            return True
        else:
            snippet = output[-300:] if output else "(no output)"
            print(
                f"  {RED}✗  iter {iteration}/{max_iter}  exit {returncode}{RST}"
                f"  {GRAY}↓ error snippet{RST}"
            )
            print(f"\n  {GRAY}{snippet}{RST}\n")
            error_out = output
            prev_code = code

            if iteration < max_iter:
                print(f"  {GOLD}↻  sending error back to model...{RST}\n")

    print(f"\n  {RED}✗  max iterations ({max_iter}) reached — no success{RST}\n")
    return False

# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def main():
    args = sys.argv[1:]
    max_iter = DEFAULT_MAX
    task = None

    # parse --max N
    filtered = []
    i = 0
    while i < len(args):
        if args[i] == "--max" and i + 1 < len(args):
            try:
                max_iter = int(args[i + 1])
            except ValueError:
                print(f"\n  {RED}--max requires an integer{RST}\n")
                sys.exit(1)
            i += 2
        else:
            filtered.append(args[i])
            i += 1

    if filtered:
        task = " ".join(filtered)

    token = load_token()
    if not token:
        print(f"\n  {RED}no token found{RST}")
        print(f"  {GRAY}write your token:   {CYAN}echo 'tok' > ~/.axis-token{RST}\n")
        sys.exit(1)

    if not task:
        try:
            task = input(
                f"\n  {PINK}{BOLD}sov-exec{RST}  {GOLD}task:{RST}  "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {GRAY}cancelled{RST}\n")
            sys.exit(0)

    if not task:
        print(f"\n  {GRAY}no task given — exiting{RST}\n")
        sys.exit(0)

    success = sov_exec(task, max_iter, token)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
