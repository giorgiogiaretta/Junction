#!/usr/bin/env bash
# One-command demo: glove (or mock) -> fanout -> dashboard + robot hand.
# Usage: demo/run_demo.sh [--real] [--backend sim|serial|pca9685|dry] [--dev /dev/ttyACM0]
# Default: mock stream + MuJoCo-free dry backend. --real = do not start mock (Rokoko Studio sends to UDP 14043).
cd "$(dirname "$0")/.."
MOCK=1; BACKEND=dry; DEV=""
while [ $# -gt 0 ]; do case "$1" in
  --real) MOCK=0;; --backend) BACKEND="$2"; shift;; --dev) DEV="--dev $2"; shift;;
esac; shift; done
PY=${PYTHON:-python3}
trap 'kill $(jobs -p) 2>/dev/null' EXIT INT TERM
$PY demo/fanout.py --out 14044 14045 &
$PY -m robot.run_udp --backend "$BACKEND" --port 14045 $DEV &
[ $MOCK = 1 ] && $PY Rokoko/src/mock_stream.py &
sleep 0.5
$PY demo/dashboard.py --port 14044
