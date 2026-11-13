#!/usr/bin/env bash
# Wakes a headless Claude every time someone posts on the board. Run in its own terminal.
# Usage: tools/agent-loop.sh "<Human>"   e.g. tools/agent-loop.sh Giorgio
NAME="${1:?usage: tools/agent-loop.sh <YourName>}"
cd "$(dirname "$0")/.."
while tools/board wait --interval 30; do
  claude -p "You are [$NAME's Claude] on the team board. Read AGENTS.md, run tools/board unread, and act on anything that mentions you or @all, or affects your folders. Work autonomously, reply on the board, commit and push your own files. Do not ask a human unless an action is destructive." \
    --permission-mode acceptEdits \
    --allowedTools "Bash(tools/board:*)" "Bash(git:*)" "Bash(gh:*)" "Bash(python:*)" "Read" "Edit" "Write" "Glob" "Grep"
done
