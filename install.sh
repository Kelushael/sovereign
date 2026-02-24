#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  sovereign — universal installer
#  works on: Debian · Ubuntu · Fedora · Arch · Alpine · macOS 10+ · WSL · Termux
#
#  curl -s https://raw.githubusercontent.com/Kelushael/sovereign/main/install.sh | bash
# ═══════════════════════════════════════════════════════════════════════════════
set -e

REPO="https://raw.githubusercontent.com/Kelushael/sovereign/main"
BIN="$HOME/.local/bin"
DEST="$BIN/sovereign"
CHERUB="$BIN/cherub"
PINK='\033[38;2;255;105;180m'; LIME='\033[38;2;57;255;100m'
CYAN='\033[38;2;0;220;255m';   GRAY='\033[38;2;85;85;105m'
RED='\033[38;2;255;70;70m';    RST='\033[0m'; BOLD='\033[1m'

echo -e "\n${PINK}${BOLD}  sovereign installer${RST}"
echo -e "  ${GRAY}zero-config · zero local compute · your stack${RST}\n"

# ── OS DETECTION ──────────────────────────────────────────────────────────────
OS="$(uname -s 2>/dev/null || echo unknown)"
DISTRO=""
[ -f /etc/os-release ] && . /etc/os-release && DISTRO="${ID:-}"

echo -e "  ${GRAY}detected: ${OS} ${DISTRO}${RST}"

# ── PACKAGE MANAGER DETECTION ─────────────────────────────────────────────────
install_pkg() {
    PKG="$1"
    if   command -v apt-get  &>/dev/null; then sudo apt-get install -y -qq "$PKG"
    elif command -v apt      &>/dev/null; then sudo apt install -y -qq "$PKG"
    elif command -v dnf      &>/dev/null; then sudo dnf install -y -q "$PKG"
    elif command -v yum      &>/dev/null; then sudo yum install -y -q "$PKG"
    elif command -v pacman   &>/dev/null; then sudo pacman -Sy --noconfirm "$PKG"
    elif command -v apk      &>/dev/null; then sudo apk add --quiet "$PKG"
    elif command -v zypper   &>/dev/null; then sudo zypper install -y "$PKG"
    elif command -v brew     &>/dev/null; then brew install "$PKG"
    elif command -v pkg      &>/dev/null; then pkg install -y "$PKG"      # Termux / FreeBSD
    elif command -v snap     &>/dev/null; then sudo snap install "$PKG"
    elif command -v nix-env  &>/dev/null; then nix-env -i "$PKG"
    else
        echo -e "  ${RED}cannot install ${PKG} — install it manually then re-run${RST}"
        return 1
    fi
}

# ── PYTHON ────────────────────────────────────────────────────────────────────
PYTHON=""
for py in python3 python3.12 python3.11 python3.10 python3.9 python3.8 python; do
    if command -v "$py" &>/dev/null; then
        VER=$("$py" -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo 0)
        [ "$VER" -ge 3 ] && PYTHON="$py" && break
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "  ${GRAY}python3 not found — installing...${RST}"
    # macOS: try homebrew first
    if [ "$OS" = "Darwin" ]; then
        if ! command -v brew &>/dev/null; then
            echo -e "  ${GRAY}installing homebrew...${RST}"
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        fi
        brew install python3
    else
        install_pkg python3 || install_pkg python
    fi
    for py in python3 python; do
        command -v "$py" &>/dev/null && PYTHON="$py" && break
    done
fi

echo -e "  ${LIME}✓${RST}  python → ${CYAN}$(command -v $PYTHON)${RST}"

# ── PIP ───────────────────────────────────────────────────────────────────────
if ! "$PYTHON" -m pip --version &>/dev/null 2>&1; then
    echo -e "  ${GRAY}pip not found — installing...${RST}"
    if [ "$OS" = "Darwin" ] || command -v brew &>/dev/null; then
        brew install python3 2>/dev/null || true
    elif command -v apt-get &>/dev/null || command -v apt &>/dev/null; then
        install_pkg python3-pip
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3-pip
    elif command -v apk &>/dev/null; then
        apk add py3-pip
    else
        curl -s https://bootstrap.pypa.io/get-pip.py | "$PYTHON"
    fi
fi

# ── REQUESTS ──────────────────────────────────────────────────────────────────
if ! "$PYTHON" -c "import requests" &>/dev/null 2>&1; then
    echo -e "  ${GRAY}installing requests...${RST}"
    "$PYTHON" -m pip install --quiet --user requests \
        || "$PYTHON" -m pip install --quiet requests \
        || sudo "$PYTHON" -m pip install --quiet requests
fi
echo -e "  ${LIME}✓${RST}  requests"

# ── CURL / WGET ───────────────────────────────────────────────────────────────
DL=""
command -v curl  &>/dev/null && DL="curl -fsSL"
command -v wget  &>/dev/null && DL="${DL:-wget -qO-}"

if [ -z "$DL" ]; then
    install_pkg curl
    DL="curl -fsSL"
fi

# ── DOWNLOAD SOVEREIGN + CHERUB ───────────────────────────────────────────────
mkdir -p "$BIN"

echo -e "  ${GRAY}downloading sovereign...${RST}"
if command -v curl &>/dev/null; then
    curl -fsSL "$REPO/sovereign.py" -o "$DEST"
    curl -fsSL "$REPO/cherub.py"    -o "$CHERUB"
else
    wget -qO "$DEST"   "$REPO/sovereign.py"
    wget -qO "$CHERUB" "$REPO/cherub.py"
fi
chmod +x "$DEST" "$CHERUB"
echo -e "  ${LIME}✓${RST}  sovereign → ${CYAN}${DEST}${RST}"
echo -e "  ${LIME}✓${RST}  cherub    → ${CYAN}${CHERUB}${RST}"

# ── PATH ──────────────────────────────────────────────────────────────────────
add_to_path() {
    local rc="$1"
    [ -f "$rc" ] || return
    grep -q "$BIN" "$rc" 2>/dev/null && return
    echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> "$rc"
    echo -e "  ${LIME}✓${RST}  added ${BIN} to PATH in ${rc}"
}

if [[ ":$PATH:" != *":$BIN:"* ]]; then
    add_to_path "$HOME/.bashrc"
    add_to_path "$HOME/.zshrc"
    add_to_path "$HOME/.bash_profile"
    add_to_path "$HOME/.profile"
    export PATH="$BIN:$PATH"
fi
echo -e "  ${LIME}✓${RST}  PATH"

# ── TOKEN ─────────────────────────────────────────────────────────────────────
if [ -f "$HOME/.axis-token" ]; then
    echo -e "  ${LIME}✓${RST}  token found at ~/.axis-token"
elif [ -n "${AXIS_TOKEN:-}" ]; then
    echo "$AXIS_TOKEN" > "$HOME/.axis-token"
    chmod 600 "$HOME/.axis-token"
    echo -e "  ${LIME}✓${RST}  token saved from env"
else
    echo -e "\n  ${GRAY}no token yet — to get one:${RST}"
    echo -e "  ${CYAN}export AXIS_TOKEN=your-token && bash install.sh${RST}"
    echo -e "  ${GRAY}or write it manually:  echo 'token' > ~/.axis-token${RST}"
fi

# ── DONE ──────────────────────────────────────────────────────────────────────
echo -e "\n${PINK}${BOLD}  sovereign is ready.${RST}\n"
echo -e "  ${LIME}sovereign${RST}  — open your stack"
echo -e "  ${LIME}cherub${RST}     — pattern watcher\n"

# If sourced in current shell, reload PATH immediately
[ -n "${BASH_VERSION:-}" ] && hash -r 2>/dev/null || true
