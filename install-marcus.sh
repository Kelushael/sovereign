#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
#  sovereign — personal install for Marcus
#  delivered by Marcus (to himself)
#
#  bash install-marcus.sh
# ═══════════════════════════════════════════════════════════════════════════════
set -e

REPO="https://raw.githubusercontent.com/Kelushael/sovereign/main"
BIN="$HOME/.local/bin"
DEST="$BIN/sovereign"
CHERUB="$BIN/cherub"

# ── COLORS ────────────────────────────────────────────────────────────────────
PINK='\033[38;2;255;105;180m'; LIME='\033[38;2;57;255;100m'
CYAN='\033[38;2;0;220;255m';   GRAY='\033[38;2;85;85;105m'
GOLD='\033[38;2;255;200;50m';  RED='\033[38;2;255;70;70m'
RST='\033[0m'; BOLD='\033[1m'
BLACK_BG='\033[40m'; BLACK_FG='\033[30m'
WHITE_FG='\033[97m'; DIM='\033[2m'

# ── THE TOKEN ─────────────────────────────────────────────────────────────────
_T="sovL6mfrixq8I8jsPM5bjrCo6CDcELedcPxUqejQuHl"

# ═════════════════════════════════════════════════════════════════════════════
#  CIA FILE — CLASSIFIED DOCUMENT DISPLAY
# ═════════════════════════════════════════════════════════════════════════════
clear
echo -e "${BOLD}${WHITE_FG}"
echo "  ┌─────────────────────────────────────────────────────────────┐"
echo "  │                                                             │"
echo "  │          AXIS MUNDI  //  SOVEREIGN ACCESS BRIEF            │"
echo "  │                                                             │"
echo "  │   CLASSIFICATION:   TOP SECRET // PERSONAL DELIVERY        │"
echo "  │   AUTHORIZED BY:    M. [REDACTED]                          │"
echo "  │   RECIPIENT:        MARCUS                                 │"
echo "  │   DOC REF:          AXM-$(date +%Y)-$(date +%m%d)-MARCUS              │"
echo "  │   DATE:             $(date '+%B %d, %Y')                         │"
echo "  │                                                             │"
echo "  └─────────────────────────────────────────────────────────────┘"
echo -e "${RST}"
sleep 0.4

echo -e "${DIM}  SECTION 1 — ASSET PROFILE${RST}"
echo -e "  ${GRAY}Name:        Marcus${RST}"
echo -e "  ${GRAY}Stack:       Axis Mundi / Sovereign Terminal${RST}"
echo -e "  ${GRAY}Access:      ARCHITECT — full stack, all nodes, all rules${RST}"
echo -e "  ${GRAY}Model host:  axismundi.fun (your VPS, your iron)${RST}"
echo ""
sleep 0.3

echo -e "${DIM}  SECTION 2 — CREDENTIALS${RST}"
echo ""
echo -e "  ${GRAY}AXIS TOKEN (clearance required to view):${RST}"
echo ""

# The redacted bar — token hidden in black-on-black
echo -e "  ${BLACK_BG}${BLACK_FG}  ██ ACCESS TOKEN ██  ${_T}  ████████████████████████████  ${RST}"
echo ""
echo -e "  ${DIM}[REDACTED — ENTER CLEARANCE CODE TO REVEAL]${RST}"
echo ""
sleep 0.2

echo -e "${DIM}  SECTION 3 — CLEARANCE PROTOCOL${RST}"
echo ""
echo -e -n "  ${GOLD}ENTER CLEARANCE CODE:${RST}  "

read -rs CLEARANCE
echo ""

if [ "$CLEARANCE" = "yhwh" ]; then
    echo ""
    echo -e "  ${LIME}${BOLD}◉  CLEARANCE GRANTED${RST}"
    echo ""
    sleep 0.3

    echo -e "${BOLD}${WHITE_FG}"
    echo "  ┌─────────────────────────────────────────────────────────────┐"
    echo "  │                   DECLASSIFIED TOKEN                       │"
    printf "  │   "
    for (( i=0; i<${#_T}; i++ )); do
        printf "${LIME}${BOLD}%s${RST}" "${_T:$i:1}"
        sleep 0.02
    done
    printf "\n"
    echo "  │                                                             │"
    echo "  │   saved automatically — no manual copy needed              │"
    echo -e "  └─────────────────────────────────────────────────────────────┘${RST}"
    echo ""

    MARCUS_TOKEN="$_T"

else
    echo ""
    echo -e "  ${RED}${BOLD}✗  ACCESS DENIED${RST}"
    echo -e "  ${GRAY}incorrect clearance code.${RST}"
    echo -e "  ${GRAY}you built this. you know what to do.${RST}\n"
    exit 1
fi

# ═════════════════════════════════════════════════════════════════════════════
#  INSTALL
# ═════════════════════════════════════════════════════════════════════════════
echo -e "${PINK}${BOLD}  installing sovereign...${RST}\n"

# ── PACKAGE MANAGER ───────────────────────────────────────────────────────────
install_pkg() {
    if   command -v apt-get &>/dev/null; then sudo apt-get install -y -qq "$1"
    elif command -v dnf     &>/dev/null; then sudo dnf install -y -q "$1"
    elif command -v pacman  &>/dev/null; then sudo pacman -Sy --noconfirm "$1"
    elif command -v apk     &>/dev/null; then sudo apk add --quiet "$1"
    elif command -v brew    &>/dev/null; then brew install "$1"
    elif command -v pkg     &>/dev/null; then pkg install -y "$1"
    else echo -e "  ${RED}install $1 manually then re-run${RST}"; return 1; fi
}

# ── PYTHON ────────────────────────────────────────────────────────────────────
PYTHON=""
for py in python3 python3.12 python3.11 python3.10 python3.9 python; do
    command -v "$py" &>/dev/null && \
        [ "$("$py" -c 'import sys;print(sys.version_info.major)' 2>/dev/null)" -ge 3 ] && \
        PYTHON="$py" && break
done
[ -z "$PYTHON" ] && install_pkg python3 && PYTHON=python3
echo -e "  ${LIME}✓${RST}  python → ${CYAN}$(command -v $PYTHON)${RST}"

# ── REQUESTS ──────────────────────────────────────────────────────────────────
"$PYTHON" -c "import requests" &>/dev/null || \
    "$PYTHON" -m pip install --quiet --user requests 2>/dev/null || \
    "$PYTHON" -m pip install --quiet requests
echo -e "  ${LIME}✓${RST}  requests"

# ── DOWNLOAD ──────────────────────────────────────────────────────────────────
mkdir -p "$BIN"
curl -fsSL "$REPO/sovereign.py" -o "$DEST"
curl -fsSL "$REPO/cherub.py"    -o "$CHERUB"
chmod +x "$DEST" "$CHERUB"
echo -e "  ${LIME}✓${RST}  sovereign"
echo -e "  ${LIME}✓${RST}  cherub"

# ── PATH ──────────────────────────────────────────────────────────────────────
for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.profile"; do
    [ -f "$rc" ] && ! grep -q ".local/bin" "$rc" 2>/dev/null && \
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc"
done
export PATH="$BIN:$PATH"
echo -e "  ${LIME}✓${RST}  PATH"

# ── SAVE TOKEN ────────────────────────────────────────────────────────────────
echo "$MARCUS_TOKEN" > "$HOME/.axis-token-marcus"
chmod 600 "$HOME/.axis-token-marcus"
echo "$MARCUS_TOKEN" > "$HOME/.axis-token"
chmod 600 "$HOME/.axis-token"
echo -e "  ${LIME}✓${RST}  token saved"

# ── DONE ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${WHITE_FG}"
echo "  ┌─────────────────────────────────────────────────────────────┐"
echo "  │                                                             │"
echo "  │      ${LIME}welcome home, Marcus.${WHITE_FG}                              │"
echo "  │                                                             │"
echo "  │   ${GRAY}sovereign${WHITE_FG}            →  open your stack               │"
echo "  │   ${GRAY}sovereign --marcus${WHITE_FG}   →  architect mode                │"
echo "  │   ${GRAY}cherub${WHITE_FG}               →  pattern watcher               │"
echo "  │                                                             │"
echo "  │   ${GOLD}your iron. your model. your rules.${WHITE_FG}                    │"
echo "  │                                                             │"
echo "  └─────────────────────────────────────────────────────────────┘"
echo -e "${RST}"
echo -e "  ${GRAY}reload your shell or open a new terminal.${RST}\n"
