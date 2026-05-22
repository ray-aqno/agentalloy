# State-inspection helpers for the sandbox container.
# Source this inside the container:  source /sandbox/helpers.sh
#
# Functions:
#   ss-install         Editable-install skillsmith from /src (the mounted host checkout)
#   ss-state           Pretty-print install-state.json
#   ss-pending         Show pending_pack_selection (the field that drives the no-double-prompt fix)
#   ss-pid             Show spawned_ollama_pid (the field that gates targeted daemon stop)
#   ss-clean           Wipe all skillsmith state — fresh-install starting point
#   ss-models          List ollama-managed models
#   ss-procs           Show running ollama/skillsmith/llama-server processes
#   ollama-up          Start ollama serve in the background (logs to /tmp/ollama.log)
#   ollama-down        Kill ollama serve (whatever PID it's at)

ss-install() {
    if [ ! -d "${SKILLSMITH_SRC:-/src}" ]; then
        echo "ERROR: ${SKILLSMITH_SRC:-/src} not found. Did you mount the host checkout?" >&2
        return 1
    fi
    uv pip install --system -e "${SKILLSMITH_SRC:-/src}" 2>&1 | tail -3
}

ss-state() {
    local fp="${XDG_CONFIG_HOME:-$HOME/.config}/skillsmith/install-state.json"
    if [ -f "$fp" ]; then
        jq . "$fp"
    else
        echo "(no state file at $fp)"
    fi
}

ss-pending() {
    local fp="${XDG_CONFIG_HOME:-$HOME/.config}/skillsmith/install-state.json"
    if [ -f "$fp" ]; then
        jq '.pending_pack_selection' "$fp"
    else
        echo "(no state file)"
    fi
}

ss-pid() {
    local fp="${XDG_CONFIG_HOME:-$HOME/.config}/skillsmith/install-state.json"
    if [ -f "$fp" ]; then
        jq '.spawned_ollama_pid' "$fp"
    else
        echo "(no state file)"
    fi
}

ss-clean() {
    rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/skillsmith"
    rm -rf "${XDG_DATA_HOME:-$HOME/.local/share}/skillsmith"
    echo "wiped skillsmith state"
}

ss-models() {
    if command -v ollama >/dev/null 2>&1; then
        ollama list 2>&1
    else
        echo "(ollama not on PATH)"
    fi
}

ss-procs() {
    echo "--- ollama ---"
    pgrep -alf ollama || echo "(none)"
    echo "--- llama-server ---"
    pgrep -alf llama-server || echo "(none)"
    echo "--- skillsmith ---"
    pgrep -alf skillsmith || echo "(none)"
}

ollama-up() {
    if pgrep -f "ollama serve" >/dev/null; then
        echo "ollama already running"
        return 0
    fi
    nohup ollama serve >/tmp/ollama.log 2>&1 &
    sleep 2
    echo "ollama spawned (pid=$!), logs: /tmp/ollama.log"
}

ollama-down() {
    pkill -f "ollama serve" && echo "ollama serve stopped" || echo "no ollama serve to stop"
}

echo "skillsmith sandbox helpers loaded. Try: ss-install, ss-clean, ss-state"
