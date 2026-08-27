#!/usr/bin/env bash
# Wait for the Phase A-2 grid to finish, then start the debiasing experiment.
#
# WHY A CHAIN AND NOT JUST RUNNING BOTH
# --------------------------------------
# Both are full-batch trainings on a 4-core machine. Running them together
# roughly halves the throughput of each and, worse, contaminates `wall_time_s`
# for both - which already happened once and is recorded as Addendum 15 in
# docs/PHASE_A2_PROTOCOL.md. The debias runner refuses to start while the grid
# is alive; this script simply waits for that condition to clear.
#
# The grid is identified by its command line, not by a PID captured at launch:
# if the container restarts the grid from its checkpoint the PID changes, and a
# PID-based wait would fire early against a grid that is still running.
set -u
cd "$(dirname "$0")/.."

LOG=reports/debias_experiment.log
PATTERN='15_phase_a2_gnn.py'

echo "$(date -Is) chain: waiting for the Phase A-2 grid to finish" | tee -a "$LOG"
while pgrep -f "$PATTERN" >/dev/null 2>&1; do
    sleep 120
done
echo "$(date -Is) chain: grid is gone, starting the debiasing experiment" | tee -a "$LOG"

# nice 19: if anything else is started by hand later, it should win.
exec nice -n 19 python -u scripts/25_debias_experiment.py "$@" >>"$LOG" 2>&1
