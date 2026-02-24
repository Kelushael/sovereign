# SOVEREIGN STACK — FINISHING DIRECTIVE
## For: Arcee / Codex / whoever holds the right terminal
## From: Claude (left terminal) — context handoff, session end

---

You are receiving this because the left terminal (Claude / sovereign) has hit context
limits. Marcus needs you to finish what was started. Here is everything you need.

---

## WHO MARCUS IS

Marcus (@Kelushael) is building a zero-config sovereign AI stack — all inference on his
own VPS, no cloud lock-in, no Ollama inside the entry terminal. He thinks in bursts.
Trust his intent over his literal words. He says "bartinkger" — he means bartowski.
He says "sight bulb" — he means screen-capture-to-AI-vision pipeline. You know what
he means.

---

## THE STACK (what exists, confirmed working)

```
sovereign.py       — entry terminal. ~/.axis-token auth. axismundi.fun VPS.
cherub.py          — pattern watcher. reads log.jsonl, proposes /addcmd entries.
sovereign-run      — VPS model swap script (NOT yet deployed to model node).
sov-voice.py       — system-wide STT. faster-whisper + xdotool.
sov-see.py         — screen grab → vision API → describes what it sees.
sov-eye.py         — screen grab → floating popup viewer.
dance.py + sh      — AI-to-AI 6-step handshake, tmux split terminal.
```

All files live at `/home/marcus/`. Linked to `~/.local/bin/` where applicable.
GitHub: Kelushael/sovereign (clean) and Kelushael/sovereign-stack (infra).

---

## THE MODEL NODE — WHAT NEEDS FINISHING

**Server:** `187.77.208.28`
**SSH key:** `~/.ssh/id_ollama` (from Marcus's laptop)
**State:** clean VPS, 368GB disk, 31GB RAM

### 1. DOWNLOAD IN PROGRESS (check first)
```bash
ssh -i ~/.ssh/id_ollama root@187.77.208.28 'ls -lh /root/axis-mundi/models/'
```
Downloading: `Qwen2.5-32B-Instruct-Q5_K_M.gguf` (~22GB, bartowski quant)
PID 473043 — confirm it's still running:
```bash
ssh -i ~/.ssh/id_ollama root@187.77.208.28 'ps aux | grep wget | grep -v grep'
```
If dead, resume with `-c` flag:
```bash
ssh -i ~/.ssh/id_ollama root@187.77.208.28 'bash -s' << 'EOF'
wget -c -O /root/axis-mundi/models/Qwen2.5-32B-Instruct-Q5_K_M.gguf \
  "https://huggingface.co/bartowski/Qwen2.5-32B-Instruct-GGUF/resolve/main/Qwen2.5-32B-Instruct-Q5_K_M.gguf" \
  >> /root/axis-mundi/models/dl.log 2>&1 &
echo "PID: $!"
EOF
```

### 2. INSTALL LLAMA-SERVER
Once download is done or while it runs:
```bash
ssh -i ~/.ssh/id_ollama root@187.77.208.28 'bash -s' << 'EOF'
apt-get update -qq
apt-get install -y cmake build-essential
# or grab prebuilt binary:
wget -q https://github.com/ggml-org/llama.cpp/releases/latest/download/llama-b5238-bin-ubuntu-x64.zip \
  -O /tmp/llama.zip && unzip -o /tmp/llama.zip -d /usr/local/bin/
chmod +x /usr/local/bin/llama-server
llama-server --version
EOF
```

### 3. SET CURRENT.GGUF SYMLINK
```bash
ssh -i ~/.ssh/id_ollama root@187.77.208.28 \
  'ln -sf /root/axis-mundi/models/Qwen2.5-32B-Instruct-Q5_K_M.gguf \
           /root/axis-mundi/models/current.gguf && echo "symlink set"'
```

### 4. CREATE axis-model.service
```bash
ssh -i ~/.ssh/id_ollama root@187.77.208.28 'bash -s' << 'EOF'
cat > /etc/systemd/system/axis-model.service << 'SVC'
[Unit]
Description=axis-model llama-server
After=network.target

[Service]
ExecStart=/usr/local/bin/llama-server \
  --model /root/axis-mundi/models/current.gguf \
  --host 0.0.0.0 \
  --port 8181 \
  --ctx-size 8192 \
  --n-gpu-layers 0 \
  --threads 8 \
  --alias axis-model
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVC
systemctl daemon-reload
systemctl enable axis-model
echo "service installed"
EOF
```

### 5. START + VERIFY
```bash
ssh -i ~/.ssh/id_ollama root@187.77.208.28 \
  'systemctl start axis-model && sleep 5 && \
   curl -s http://127.0.0.1:8181/v1/models | python3 -m json.tool'
```

---

## WHAT ELSE IS PENDING

**sov-see vision:** needs `~/.anthropic-token` on Marcus's laptop with Anthropic API key.

**dance.py right side:** needs `~/.arcee-token` with Arcee API key.

**sovereign-run deploy:** push the deploy script from `/home/marcus/sovereign-stack/` to the
model node so Marcus can hot-swap models with one command.

**sovereign-install one-liner:** `curl -s https://axismundi.fun/me | bash`
Installs token + sovereign to PATH on any Marcus machine. Not built yet.

**gift version:** `sovereign-gift.py` — clean template for others. Wait until sovereign.py
confirmed working end-to-end first.

---

## ARCHITECTURE

```
Marcus laptop
  sovereign.py ──► axismundi.fun (76.13.24.113, nginx/SSL)
                        │
                        └──► 187.77.208.28:8181 (llama-server, axis-model.service)
                                    │
                             /root/axis-mundi/models/current.gguf  ← symlink
                             Qwen2.5-32B-Instruct-Q5_K_M.gguf      ← the model
```

---

## TONE / WORKING STYLE

- Keep it sovereign-clean. No bloat. No emoji spam. No over-engineering.
- One script does one thing well.
- ANSI colors: PINK/LIME/CYAN/GOLD/GRAY — match the palette.
- Zero-config is sacred. Read tokens from `~/.*-token` files first.
- Marcus trusts you. "Whatever you do is trusted." Don't abuse it.

---

**The left terminal finished its context. The right terminal carries it forward.**
**The dance continues.**
