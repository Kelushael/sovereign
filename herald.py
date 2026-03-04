#!/usr/bin/env python3
"""herald — sovereign setup wizard"""

import os
import sys
import stat
import json
import urllib.request
import urllib.error

# ANSI colors
PINK  = "\033[38;5;213m"
LIME  = "\033[38;5;154m"
CYAN  = "\033[38;5;51m"
GOLD  = "\033[38;5;220m"
GRAY  = "\033[38;5;245m"
RED   = "\033[38;5;196m"
RST   = "\033[0m"
BOLD  = "\033[1m"

GATEWAY       = "https://axismundi.fun"
TOKEN_PATH    = os.path.expanduser("~/.axis-token")
SOVEREIGN_BIN = os.path.expanduser("~/.local/bin/sovereign")
CHERUB_BIN    = os.path.expanduser("~/.local/bin/cherub")
SOVEREIGN_URL = "https://raw.githubusercontent.com/Kelushael/sovereign/main/sovereign.py"
CHERUB_URL    = "https://raw.githubusercontent.com/Kelushael/sovereign/main/cherub.py"


def banner():
    print(f"""
{PINK}{BOLD}  ██╗  ██╗███████╗██████╗  █████╗ ██╗     ██████╗{RST}
{PINK}{BOLD}  ██║  ██║██╔════╝██╔══██╗██╔══██╗██║     ██╔══██╗{RST}
{PINK}{BOLD}  ███████║█████╗  ██████╔╝███████║██║     ██║  ██║{RST}
{PINK}{BOLD}  ██╔══██║██╔══╝  ██╔══██╗██╔══██║██║     ██║  ██║{RST}
{PINK}{BOLD}  ██║  ██║███████╗██║  ██║██║  ██║███████╗██████╔╝{RST}
{PINK}{BOLD}  ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═════╝{RST}

{CYAN}  sovereign setup wizard{RST}
{GRAY}  mesh node onboarding — axismundi.fun{RST}
""")


def ask(prompt, default=None):
    indicator = f" [{default}]" if default else ""
    try:
        val = input(f"{GOLD}  > {prompt}{indicator}: {RST}").strip()
    except (KeyboardInterrupt, EOFError):
        print(f"\n{GRAY}  Aborted.{RST}")
        sys.exit(0)
    return val if val else (default or "")


def ok(msg):
    print(f"  {LIME}✓{RST} {msg}")


def err(msg):
    print(f"  {RED}✗{RST} {msg}")


def info(msg):
    print(f"  {CYAN}·{RST} {msg}")


def section(title):
    print(f"\n{BOLD}{GOLD}  — {title}{RST}")


def read_token():
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH) as f:
            return f.read().strip()
    return None


def write_token(token):
    os.makedirs(os.path.dirname(TOKEN_PATH) or ".", exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        f.write(token.strip())
    os.chmod(TOKEN_PATH, stat.S_IRUSR | stat.S_IWUSR)


def check_connectivity(token):
    url = f"{GATEWAY}/v1/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            models = data.get("data", [])
            if models:
                return True, models[0].get("id", "axis-model")
            return True, "axis-model"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, str(e.reason)
    except Exception as e:
        return False, str(e)


def gateway_reachable():
    try:
        urllib.request.urlopen(f"{GATEWAY}/v1/models", timeout=5)
        return True
    except Exception:
        return False


def already_configured():
    token = read_token()
    if not token:
        return False, None, None
    reachable, model = check_connectivity(token)
    return reachable, token, model


def download_bin(url, dest, label):
    info(f"Downloading {label}...")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        urllib.request.urlretrieve(url, dest)
        os.chmod(dest, os.stat(dest).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        ok(f"{label} installed → {dest}")
        return True
    except Exception as e:
        err(f"Could not download {label}: {e}")
        return False


def step_token():
    section("Step 1 — axis token")
    info("Your token authenticates you to the sovereign mesh.")
    ans = ask("Do you have an axis token? (y/n)", "n").lower()
    if ans not in ("y", "yes"):
        print(f"""
{CYAN}  To get a token:{RST}
{GRAY}  1. Visit {GATEWAY}
  2. Contact the mesh operator for access
  3. Re-run herald once you have your token{RST}
""")
        sys.exit(0)

    token = ask("Paste your token")
    if not token:
        err("No token entered. Exiting.")
        sys.exit(1)
    return token


def step_connect(token):
    section("Step 2 — test connectivity")
    info(f"Reaching {GATEWAY} ...")
    ok_conn, model_or_err = check_connectivity(token)
    if ok_conn:
        ok(f"Connected!  Model: {LIME}{model_or_err}{RST}")
        return True
    else:
        err(f"Connection failed: {model_or_err}")
        info("Check your token and network, then re-run herald.")
        return False


def step_install():
    section("Step 3 — install sovereign + cherub")
    installed = []

    if os.path.exists(SOVEREIGN_BIN):
        ok(f"sovereign already present → {SOVEREIGN_BIN}")
    else:
        if download_bin(SOVEREIGN_URL, SOVEREIGN_BIN, "sovereign"):
            installed.append("sovereign")

    if os.path.exists(CHERUB_BIN):
        ok(f"cherub already present → {CHERUB_BIN}")
    else:
        if download_bin(CHERUB_URL, CHERUB_BIN, "cherub"):
            installed.append("cherub")

    local_bin = os.path.expanduser("~/.local/bin")
    path_env = os.environ.get("PATH", "")
    if local_bin not in path_env:
        info(f"Add to your shell profile: {GRAY}export PATH=\"$HOME/.local/bin:$PATH\"{RST}")


def step_role():
    section("Step 4 — node role (optional)")
    print(f"""  {GRAY}Roles:{RST}
    {CYAN}controller{RST}  — run sovereign here and issue tasks
    {CYAN}architect{RST}   — build and run code on this machine
    {CYAN}server{RST}      — this machine serves the model (GGUF)
    {CYAN}skip{RST}        — configure later
""")
    role = ask("Role for this machine? [controller/architect/server/skip]", "skip").lower()

    if role == "controller":
        ok("Controller node configured.")
        info("Run sovereign to start issuing tasks across the mesh.")

    elif role == "architect":
        ok("Architect node configured.")
        ans = ask("Install sov-exec (code runner)? (y/n)", "n").lower()
        if ans in ("y", "yes"):
            sov_exec = os.path.expanduser("~/.local/bin/sov-exec")
            sov_exec_url = "https://raw.githubusercontent.com/Kelushael/sovereign/main/sov-exec.py"
            download_bin(sov_exec_url, sov_exec, "sov-exec")
        else:
            info("Skipped sov-exec. Install manually later if needed.")

    elif role == "server":
        ok("Server node noted.")
        info("Point axis-model.service at your GGUF file in /root/axis-mundi/models/")
        info("Use sovereign-run to swap models live.")

    else:
        info("Role skipped. You can re-run herald anytime to reconfigure.")


def show_summary(token, model):
    masked = token[:8] + "..." + token[-4:] if len(token) > 14 else "***"
    print(f"""
{BOLD}{LIME}  Already configured!{RST}  Run {CYAN}sovereign{RST} to start.

  {GRAY}token:{RST}  {masked}
  {GRAY}model:{RST}  {model}
  {GRAY}gate:{RST}   {GATEWAY}
  {GRAY}token file:{RST} {TOKEN_PATH}
""")


def show_quickref():
    print(f"""
{BOLD}{GOLD}  Quick reference:{RST}
  {CYAN}sovereign{RST}            — open the terminal
  {CYAN}cherub{RST}               — start the pattern watcher
  {CYAN}/addcmd <name> <cmd>{RST} — add a custom command
  {CYAN}/run <task>{RST}          — run a task via the model
  {CYAN}/help{RST}                — list all commands

  {GRAY}Config dir:  ~/.config/axis-mundi/{RST}
  {GRAY}Token file:  {TOKEN_PATH}{RST}
  {GRAY}Gateway:     {GATEWAY}{RST}
""")


def main():
    banner()

    configured, token, model = already_configured()
    if configured:
        show_summary(token, model)
        sys.exit(0)

    # Step 1 — get token
    token = step_token()

    # Step 2 — test connectivity (abort if fails)
    if not step_connect(token):
        sys.exit(1)

    # Save token only after confirmed working
    write_token(token)
    ok(f"Token saved → {TOKEN_PATH}")

    # Step 3 — install binaries
    step_install()

    # Step 4 — node role
    step_role()

    # Done
    print(f"\n{BOLD}{LIME}  ✓ Setup complete.{RST}  Run: {CYAN}sovereign{RST}\n")
    show_quickref()


if __name__ == "__main__":
    main()
