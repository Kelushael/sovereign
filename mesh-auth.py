#!/usr/bin/env python3
"""
mesh-auth
=========
Joins any machine into the Axis Mundi mesh.
Run on your laptop, mini PC, hotel machine — anywhere.

  curl https://axismundi.fun/mesh-auth.py | python3

  python3 mesh-auth.py                              # register + stay alive
  python3 mesh-auth.py --requests 192.168.4.38      # proxy that host into mesh
  python3 mesh-auth.py --requests 192.168.4.38:8888 # specific port
  python3 mesh-auth.py --requests 192.168.4.0/24    # whole subnet (any port)
"""
import os, sys, json, time, socket, threading, argparse
import urllib.request, urllib.error, urllib.parse

# ── config ────────────────────────────────────────────────────────────────────
SERVER = "https://axismundi.fun"
POLL   = 3    # seconds between room bus polls

PINK = "\033[38;2;255;105;180m"
LIME = "\033[38;2;57;255;100m"
CYAN = "\033[38;2;0;220;255m"
GOLD = "\033[38;2;255;200;50m"
GRAY = "\033[38;2;85;85;105m"
RED  = "\033[38;2;255;70;70m"
PURP = "\033[38;2;180;100;255m"
RST  = "\033[0m"
BOLD = "\033[1m"

# ── token ─────────────────────────────────────────────────────────────────────
def load_token():
    for src in [
        lambda: open(os.path.expanduser("~/.axis-token")).read().strip(),
        lambda: json.load(open(os.path.expanduser("~/.config/axis-mundi/config.json"))).get("token",""),
        lambda: os.environ.get("AXIS_TOKEN",""),
    ]:
        try:
            t = src()
            if t: return t
        except: pass
    return ""

# ── http helpers ──────────────────────────────────────────────────────────────
def _get(url, token):
    req = urllib.request.Request(url)
    if token: req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}"), e.code
    except Exception as e:
        return {"error": str(e)}, 0

def _post(url, body, token):
    data = json.dumps(body).encode()
    req  = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}"), e.code
    except Exception as e:
        return {"error": str(e)}, 0

# ── local proxy request ───────────────────────────────────────────────────────
def proxy_request(target_host, target_port, path="/", method="GET", headers=None, body=None):
    """Hit a local LAN address and return the response."""
    url = f"http://{target_host}:{target_port}{path}"
    req = urllib.request.Request(url, method=method)
    if headers:
        for k, v in (headers or {}).items():
            try: req.add_header(k, v)
            except: pass
    if body:
        req.data = body.encode() if isinstance(body, str) else body
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            content = r.read()
            content_type = r.headers.get("Content-Type", "text/plain")
            try:   text = content.decode("utf-8", errors="replace")[:8000]
            except: text = repr(content[:2000])
            return {"ok": True, "status": r.status, "body": text,
                    "content_type": content_type, "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}

# ── parse targets ─────────────────────────────────────────────────────────────
def parse_target(s):
    """'192.168.4.38' or '192.168.4.38:8888' → (host, port or None)"""
    if ":" in s and not s.startswith("http"):
        parts = s.rsplit(":", 1)
        try:    return parts[0], int(parts[1])
        except: return s, None
    return s, None

# ── register this machine ─────────────────────────────────────────────────────
def register(token, targets, node_id):
    hostname = socket.gethostname()
    payload  = {
        "node_id":    node_id,
        "hostname":   hostname,
        "type":       "operator",
        "platform":   sys.platform,
        "proxies":    targets,
        "mesh_auth":  True,
        "ts":         int(time.time()),
    }
    data, status = _post(f"{SERVER}/amallo/nodes/register", payload, token)
    return status in (200, 201)

# ── room bus poll loop ────────────────────────────────────────────────────────
def room_loop(token, node_id, targets):
    """
    Poll the room bus. Handle messages of type:
      {type: "proxy", for: <node_id>, host: "192.168.4.38", port: 8888, path: "/"}
      {type: "ping",  for: <node_id>}
    Post results back.
    """
    last_ts = int(time.time())
    print(f"  {GRAY}polling mesh room bus every {POLL}s...{RST}")

    while True:
        try:
            data, _ = _get(f"{SERVER}/amallo/room?since={last_ts}", token)
            msgs = data.get("messages", [])
            for m in msgs:
                last_ts = max(last_ts, m.get("ts", 0))
                # only handle messages for us or broadcast
                for_field = m.get("for", "all")
                if for_field not in ("all", node_id, "operator"):
                    continue

                mtype = m.get("type", "")

                if mtype == "ping":
                    print(f"\n  {GOLD}◉ ping from {m.get('agent','?')}{RST}")
                    _post(f"{SERVER}/amallo/room", {
                        "agent": node_id, "type": "pong",
                        "text": f"pong from {socket.gethostname()}",
                        "for": m.get("agent", "all"),
                    }, token)

                elif mtype == "proxy":
                    host = m.get("host", "")
                    port = int(m.get("port", 80))
                    path = m.get("path", "/")
                    meth = m.get("method", "GET").upper()
                    body = m.get("body")

                    # check allowed targets
                    allowed = _is_allowed(host, port, targets)
                    if not allowed:
                        print(f"\n  {RED}✗ proxy blocked: {host}:{port} not in allowed targets{RST}")
                        _post(f"{SERVER}/amallo/room", {
                            "agent": node_id, "type": "proxy_result",
                            "text": json.dumps({"ok": False, "error": f"{host}:{port} not allowed"}),
                            "for": m.get("agent", "all"),
                        }, token)
                        continue

                    print(f"\n  {CYAN}⚙ proxy → {meth} {host}:{port}{path}{RST}")
                    result = proxy_request(host, port, path, meth, body=body)
                    status_color = LIME if result.get("ok") else RED
                    print(f"  {status_color}↩ {result.get('status', 'err')}{RST}  {result.get('body','')[:80]}")

                    _post(f"{SERVER}/amallo/room", {
                        "agent": node_id, "type": "proxy_result",
                        "text": json.dumps(result)[:4000],
                        "for": m.get("agent", "all"),
                    }, token)

                elif mtype == "status":
                    _post(f"{SERVER}/amallo/room", {
                        "agent": node_id, "type": "status_reply",
                        "text": json.dumps({
                            "hostname": socket.gethostname(),
                            "platform": sys.platform,
                            "proxies": targets,
                            "uptime": int(time.time()),
                        }),
                        "for": m.get("agent", "all"),
                    }, token)

        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"  {RED}room poll error: {e}{RST}")

        time.sleep(POLL)

# ── allowed target check ──────────────────────────────────────────────────────
def _is_allowed(host, port, targets):
    if not targets:
        return False
    for t in targets:
        t_host, t_port = parse_target(t)
        if t_host == host or host.startswith(t_host.rstrip("0123456789").rstrip(".")):
            if t_port is None or t_port == port:
                return True
    return False

# ── heartbeat ─────────────────────────────────────────────────────────────────
def heartbeat_loop(token, node_id, targets):
    while True:
        time.sleep(60)
        try:
            register(token, targets, node_id)
        except: pass

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="Join this machine into the Axis Mundi mesh")
    p.add_argument("--requests", dest="targets", nargs="+", metavar="HOST[:PORT]",
                   help="Local LAN hosts/ports the mesh is allowed to reach through you")
    p.add_argument("--token", help="Axis token (default: ~/.axis-token)")
    p.add_argument("--server", default=SERVER, help=f"Mesh server (default: {SERVER})")
    args = p.parse_args()

    global SERVER
    SERVER = args.server

    print(f"\n  {PURP}{BOLD}mesh-auth{RST}  {GRAY}— axis mundi local bridge{RST}\n")

    token = args.token or load_token()
    if not token:
        print(f"  {RED}no token — write it:{RST}  echo 'your-token' > ~/.axis-token\n")
        sys.exit(1)

    targets  = args.targets or []
    hostname = socket.gethostname()
    node_id  = f"op-{hostname}-{socket.gethostbyname(socket.gethostname())}"

    # ── connect ────────────────────────────────────────────────────────────────
    print(f"  {GRAY}connecting to {SERVER}...{RST}")
    ok = register(token, targets, node_id)
    if not ok:
        print(f"  {RED}✗ failed to register with mesh — check token{RST}\n")
        sys.exit(1)

    print(f"  {LIME}✓ registered:{RST}  {CYAN}{node_id}{RST}")

    if targets:
        print(f"  {LIME}✓ proxying:{RST}")
        for t in targets:
            h, po = parse_target(t)
            port_str = f":{po}" if po else " (any port)"
            print(f"     {GOLD}{h}{port_str}{RST}  →  mesh can reach this")

        # quick local test
        for t in targets:
            h, po = parse_target(t)
            test_port = po or 80
            result = proxy_request(h, test_port)
            if result.get("ok"):
                print(f"\n  {LIME}✓ local test OK:{RST}  {h}:{test_port}  →  HTTP {result['status']}")
                # announce on room bus
                _post(f"{SERVER}/amallo/room", {
                    "agent": node_id, "type": "say",
                    "text": f"{hostname} online — proxying {h}:{test_port} (HTTP {result['status']})",
                    "for": "all",
                }, token)
            else:
                print(f"\n  {GOLD}⚠ local test:{RST}  {h}:{test_port}  →  {result.get('error','unreachable')}")
                print(f"  {GRAY}(mesh will still be able to request it — it might need auth or a specific path){RST}")
    else:
        print(f"  {GRAY}no --requests targets — running as presence-only node{RST}")
        print(f"  {GRAY}use --requests 192.168.4.38:8888 to proxy a local address{RST}")

    print(f"\n  {GRAY}watching mesh room bus — Ctrl-C to disconnect{RST}\n")

    # heartbeat in background
    t = threading.Thread(target=heartbeat_loop, args=(token, node_id, targets), daemon=True)
    t.start()

    try:
        room_loop(token, node_id, targets)
    except KeyboardInterrupt:
        print(f"\n  {GRAY}✦  mesh-auth disconnected{RST}\n")

if __name__ == "__main__":
    main()
