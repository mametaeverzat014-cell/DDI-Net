#!/usr/bin/env bash
# Third link of the chain: wait for the debiasing experiment to COMPLETE, then
# run the Phase A-2 ensemble stage.
#
# WHY A POSITIVE COMPLETION CONDITION AND NOT "THE PROCESS IS GONE"
# ------------------------------------------------------------------
# Waiting for absence would fire immediately, because at the moment this script
# starts the debias runner has not been launched yet - the grid is still going.
# So we wait for the debias results file to contain all EXPECTED_RUNS distinct
# (cell, condition, seed) combinations. That is true only after the experiment
# has actually finished, and it is false both before it starts and while it runs.
#
# If the debias experiment dies part-way the condition never becomes true and
# the ensemble never starts. That is the intended failure mode: firing early
# would put two full-batch trainings on four cores and contaminate both, which
# already happened once (docs/PHASE_A2_PROTOCOL.md, Addendum 15).
#
# WHY THE ENSEMBLE IS RE-RUN RATHER THAN REUSED
# ----------------------------------------------
# reports/phase_a2_ensemble_BROKEN_150steps.csv exists but predates two fixes:
# the set_seed-before-construction ordering (LIMITATIONS.md 6b) and the step
# budget (Addendum 9). Reusing it would mix two code versions inside one
# pre-registered experiment.
set -u
cd "$(dirname "$0")/.."

LOG=reports/ensemble_stage.log
DEBIAS_CSV=reports/debias_results.csv
EXPECTED_RUNS=30

echo "$(date -Is) chain: waiting for the debiasing experiment to complete" | tee -a "$LOG"
while true; do
    if [ -s "$DEBIAS_CSV" ]; then
        n=$(python - <<'PY' 2>/dev/null || echo 0
import pandas as pd
d = pd.read_csv("reports/debias_results.csv")
print(len(d[["scheme", "negatives", "condition", "seed"]].drop_duplicates()))
PY
)
        [ "${n:-0}" -ge "$EXPECTED_RUNS" ] && break
    fi
    sleep 120
done
echo "$(date -Is) chain: debiasing done, starting the ensemble stage" | tee -a "$LOG"

# Same budget as the grid: a member trained under a different cap would not be
# comparable with the grid rows it is meant to be read against.
exec nice -n 19 python -u scripts/15_phase_a2_gnn.py \
    --stage ensemble --max-epochs 800 --patience 80 >>"$LOG" 2>&1
