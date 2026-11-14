#!/usr/bin/env bash
# Overnight batch: NO Claude tokens. Runs tests, replays every episode, and (if VERDA_INFERENCE_KEY is set) the Nemotron episode judge.
# Results in data/overnight/<timestamp>/ (not committed). Usage: caffeinate -i demo/overnight.sh   (Mac plugged in, lid OPEN)
cd "$(dirname "$0")/.."
OUT="data/overnight/$(date +%Y%m%d_%H%M)"; mkdir -p "$OUT"; PY=${PYTHON:-python3}
echo "start $(date)" > "$OUT/log.txt"
$PY -m pytest tests -q > "$OUT/pytest.txt" 2>&1; echo "pytest exit $?" >> "$OUT/log.txt"
$PY -m robot.replay_all --out "$OUT/replay_all.json" > "$OUT/replay_all.txt" 2>&1; echo "replay_all exit $?" >> "$OUT/log.txt"
if [ -n "$VERDA_INFERENCE_KEY" ] || [ -n "$NVIDIA_API_KEY" ]; then
  $PY -m ai.judge --out "$OUT/judge.jsonl" > "$OUT/judge.txt" 2>&1; echo "judge exit $?" >> "$OUT/log.txt"
else echo "judge skipped: no API key in the environment" >> "$OUT/log.txt"; fi
echo "done $(date)" >> "$OUT/log.txt"; cat "$OUT/log.txt"
