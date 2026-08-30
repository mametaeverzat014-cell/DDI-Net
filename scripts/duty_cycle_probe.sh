#!/usr/bin/env bash
# One line per wake-up: how long this container has been alive, and how far the
# grid has got. Consecutive lines give the duty cycle -- the fraction of wall
# time the grid is actually computing rather than waiting for a wake-up to
# recreate its container. Without it, the wake-up interval is guesswork.
cd /home/user/DDI-Net
UP=$(awk '{printf "%.0f", $1/60}' /proc/uptime)
DONE=$(python -c "import json;print(json.load(open('reports/v2_grid/progress.json'))['completed'])" 2>/dev/null || echo "?")
CK=$(ls -t reports/v2_checkpoints/*.pt 2>/dev/null | head -1)
CKAGE=$([ -n "$CK" ] && echo $(( ($(date +%s) - $(stat -c %Y "$CK")) / 60 )) || echo "?")
STEP=$(grep -c "^resumed\|^  ok " reports/v2_grid/grid_runner.log 2>/dev/null || echo 0)
printf '%s up_min=%s completed=%s newest_ckpt_age_min=%s\n' \
    "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$UP" "$DONE" "$CKAGE" \
    >> reports/v2_grid/duty_cycle.log
tail -6 reports/v2_grid/duty_cycle.log
