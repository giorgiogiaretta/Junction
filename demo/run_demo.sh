#!/usr/bin/env bash
# One-command demo: glove (or mock) -> fanout -> dashboard + robot hand.
# --bimanual: listen to the two-glove stream (14053; rgmp_client --bimanual-port 14053), --hand left|right: glove that drives the robot hand.
# Usage: demo/run_demo.sh [--real] [--bimanual] [--hand left|right] [--assist cup|egg|can] [--backend sim|serial|pca9685|dry] [--dev /dev/ttyACM0]
# Default: mock stream + MuJoCo-free dry backend. --real = do not start mock (Rokoko Studio sends to UDP 14043).
cd "$(dirname "$0")/.."
MOCK=1; BACKEND=dry; DEV=""; ASSIST=""; IN=14043; HAND=right
while [ $# -gt 0 ]; do case "$1" in
  --real) MOCK=0;; --bimanual) IN=14053;; --hand) HAND="$2"; shift;; --assist) ASSIST="--assist $2"; shift;; --backend) BACKEND="$2"; shift;; --dev) DEV="--dev $2"; shift;;
esac; shift; done
PY=${PYTHON:-python3}
trap 'kill $(jobs -p) 2>/dev/null' EXIT INT TERM
$PY demo/fanout.py --in $IN --out 14044 14045 &
$PY -m robot.run_udp --backend "$BACKEND" --port 14045 --hand $HAND $ASSIST $DEV &
[ $MOCK = 1 ] && $PY Rokoko/src/mock_stream.py &
sleep 0.5
$PY demo/dashboard.py --port 14044
