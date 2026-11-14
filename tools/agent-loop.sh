#!/usr/bin/env bash
# Wakes a headless agent every time someone posts on the board, and also every IDLE_MIN minutes of silence (so nobody sits idle while humans sleep).
# Run in its OWN git worktree/terminal. Usage: tools/agent-loop.sh "<Human>"      AGENT=claude (default) | codex
#   AGENT=codex tools/agent-loop.sh Tommaso      (Codex CLI: `codex exec --full-auto`; check `codex exec --help` on your version)
NAME="${1:?usage: tools/agent-loop.sh <YourName>}"
AGENT="${AGENT:-claude}"; IDLE_MIN="${IDLE_MIN:-25}"
cd "$(dirname "$0")/.."
LABEL="$(echo "${AGENT:0:1}" | tr a-z A-Z)${AGENT:1}"
BASE="You are [$NAME's $LABEL] on the team board. Read AGENTS.md first (shared rules, ownership, branch+PR workflow), run tools/board unread. CREDITS: delegate by default with the delegate tool (gemini-pro: long reading/summaries; gemini-flash: bulk/boilerplate; qwen-max: multi-file code/debug; deepseek: new code/math; send the same hard question blind to two models). Delegate heavy non-private work so work continues when your own credits run low, but YOU keep the final review and safety of every result: run the tests before committing."
run_agent() {
  if [ "$AGENT" = codex ]; then
    codex exec --full-auto "$1"
  else
    claude -p "$1" --permission-mode acceptEdits \
      --allowedTools "Bash(tools/board:*)" "Bash(git:*)" "Bash(gh:*)" "Bash(python:*)" "mcp__delegate__delegate" "mcp__delegate__delegate_receipts" "Read" "Edit" "Write" "Glob" "Grep"
  fi
}
while true; do
  timeout $((IDLE_MIN * 60)) tools/board wait --interval 30; rc=$?
  if [ $rc -eq 124 ]; then
    run_agent "$BASE No new posts for $IDLE_MIN minutes: do NOT idle. Pick the next unblocked item in docs/TOMORROW.md or the open issues you own, work on it with mocks/replays (no hardware), test it, push a branch/PR, post a short result. If nothing is unblocked, say so in one line and stop. Never touch another teammate's folders; never post just to acknowledge."
  elif [ $rc -eq 0 ]; then
    run_agent "$BASE Act on anything that mentions you or @all, or affects your folders. Work autonomously, reply on the board, commit and push your own files. Do not ask a human unless an action is destructive."
  else break; fi
done
