#!/bin/bash
# dance.sh — launch the sovereign AI handshake in a tmux split
#
# Left:  CLAUDE  (axismundi.fun)
# Right: ARCEE   (models.arcee.ai)
#
# Usage: bash dance.sh

DANCE="python3 /home/marcus/dance.py"

if ! command -v tmux &>/dev/null; then
    echo "need tmux:  apt install tmux"
    exit 1
fi

# kill any old dance session
tmux kill-session -t dance 2>/dev/null

tmux new-session -d -s dance -x 220 -y 50

# left pane — starts first, initialises the bus
tmux send-keys -t dance "$DANCE left" Enter

# right pane — starts 1s later, waits for left
tmux split-window -t dance -h
tmux send-keys -t dance:0.1 "sleep 1 && $DANCE right" Enter

# focus left
tmux select-pane -t dance:0.0

# attach
tmux attach-session -t dance
