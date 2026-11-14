#!/usr/bin/env bash
# PM / watchdog: every PM_INTERVAL_MIN minutes (default 60) a headless read-only Claude refreshes STATUS.md (untracked) and posts a short status on the board.
# Run it from its own worktree:  git worktree add ../Junction-pm -b pm/watch origin/main ; cd ../Junction-pm ; bash tools/pm-loop.sh
# Env: PM_INTERVAL_MIN, PM_MODEL (default sonnet), PM_ONCE=1 to run one round and exit.
cd "$(dirname "$0")/.."
INTERVAL="${PM_INTERVAL_MIN:-60}"; MODEL="${PM_MODEL:-sonnet}"
while true; do
  git fetch -q origin; git merge -q --ff-only origin/main 2>/dev/null || git reset -q --hard origin/main
  claude -p "$(cat docs/PM_PROMPT.md)" --model "$MODEL" --permission-mode acceptEdits \
    --allowedTools "Bash(tools/board:*)" "Bash(git:*)" "Bash(gh:*)" "Bash(python3:*)" "Read" "Glob" "Grep" "Write"
  [ -n "$PM_ONCE" ] && break
  sleep $((INTERVAL * 60))
done
