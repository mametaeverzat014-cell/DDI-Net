#!/usr/bin/env bash
# Keeps the V2 grid runner alive across a multi-day run.
#
# The runner writes a checkpoint every 5 validation checks and resumes from it,
# so an unattended death costs minutes, not a whole run -- but only if something
# restarts it. Waiting for a human or a scheduled check-in to notice costs hours
# of idle machine on a grid that already takes days.
#
# Liveness is tracked by PID, never by matching the command line. `pgrep -f`
# matches ANY process whose arguments contain the pattern, including an
# unrelated shell command that merely mentions the runner's filename -- a
# scheduled check-in that says "restart 34_v2_grid_runner.py" is enough. That
# reads as "the grid is alive" at exactly the moment it is not, which is the one
# reading a supervisor must never get wrong.
#
# It deliberately does NOT paper over a broken grid: consecutive restarts that
# make no progress are a real fault, and the supervisor gives up loudly rather
# than restarting forever.

set -uo pipefail
cd /home/user/DDI-Net

RUNNER="${GRID_RUNNER:-scripts/34_v2_grid_runner.py}"
LOG="${GRID_LOG:-reports/v2_grid/grid_runner.log}"
SUP_LOG="${GRID_SUP_LOG:-reports/v2_grid/supervisor.log}"
PROGRESS="${GRID_PROGRESS:-reports/v2_grid/progress.json}"
PIDFILE="${GRID_PIDFILE:-reports/v2_grid/runner.pid}"
# 24 after amendment 2 cut the grid to a 2^(5-2) fraction x 3 seeds. A stale
# total would keep the supervisor running forever past a finished grid.
TOTAL="${GRID_TOTAL:-24}"
POLL_S="${GRID_POLL_S:-300}"
MAX_STALE_RESTARTS="${GRID_MAX_STALE:-3}"

say() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*" >> "$SUP_LOG"; }

completed() {
    python -c "import json;print(json.load(open('$PROGRESS'))['completed'])" 2>/dev/null || echo -1
}

# Find an already-running runner by inspecting /proc directly: argv[0] must be a
# python interpreter and some later argument must be the runner script. A shell
# that merely mentions the script name has a shell as argv[0] and is skipped.
adopt_pid() {
    local pid argv0 hit
    for pid in $(ls /proc 2>/dev/null | grep -E '^[0-9]+$'); do
        [ -r "/proc/$pid/cmdline" ] || continue
        mapfile -d '' -t argv < "/proc/$pid/cmdline" 2>/dev/null || continue
        [ "${#argv[@]}" -gt 1 ] || continue
        argv0=$(basename -- "${argv[0]}")
        case "$argv0" in python*) ;; *) continue ;; esac
        hit=""
        for a in "${argv[@]:1}"; do
            case "$a" in *"$(basename -- "$RUNNER")") hit=1 ;; esac
        done
        [ -n "$hit" ] && { echo "$pid"; return 0; }
    done
    return 1
}

alive() { [ -n "${1:-}" ] && kill -0 "$1" 2>/dev/null; }

start_runner() {
    nohup python -u "$RUNNER" --execute >> "$LOG" 2>&1 &
    RUNNER_PID=$!
    echo "$RUNNER_PID" > "$PIDFILE"
    say "started runner pid $RUNNER_PID"
}

say "supervisor started (poll ${POLL_S}s, total ${TOTAL})"

RUNNER_PID=""
if RUNNER_PID=$(adopt_pid); then
    echo "$RUNNER_PID" > "$PIDFILE"
    say "adopted running runner pid $RUNNER_PID"
else
    # Start immediately rather than idling until the first poll. The common
    # reason no runner is present at startup is that the container was just
    # recreated and killed it, which is exactly when waiting wastes machine.
    RUNNER_PID=""
    say "no runner found at startup"
    start_runner
fi

stale=0
last_completed=$(completed)

while true; do
    sleep "$POLL_S"

    if alive "$RUNNER_PID"; then
        now=$(completed)
        if [ "$now" != "$last_completed" ]; then
            stale=0                    # progress happened; restart budget resets
            last_completed="$now"
        fi
        continue
    fi

    now=$(completed)
    if [ "$now" = "$TOTAL" ]; then
        say "grid reports $TOTAL/$TOTAL complete; supervisor exiting"
        rm -f "$PIDFILE"
        exit 0
    fi

    # Someone may have restarted it by hand; adopt rather than double-start.
    if RUNNER_PID=$(adopt_pid); then
        echo "$RUNNER_PID" > "$PIDFILE"
        say "adopted externally started runner pid $RUNNER_PID at $now/$TOTAL"
        continue
    fi
    RUNNER_PID=""

    if [ "$now" = "$last_completed" ]; then
        stale=$((stale + 1))
    else
        stale=0
        last_completed="$now"
    fi

    if [ "$stale" -gt "$MAX_STALE_RESTARTS" ]; then
        say "GIVING UP: $stale restarts with no completed run (stuck at $now/$TOTAL)."
        say "This is a fault to diagnose, not to restart around."
        rm -f "$PIDFILE"
        exit 1
    fi

    say "runner dead at $now/$TOTAL - restarting (stale streak $stale)"
    start_runner
done
