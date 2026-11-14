#!/usr/bin/env bash
# One-command demo: glove (or mock) -> fanout -> dashboard + robot hand.
# --bimanual: listen to the two-glove stream (14053; rgmp_client --bimanual-port 14053), --hand left|right: glove that drives the robot hand.
# Usage: demo/run_demo.sh [--real] [--bimanual] [--hand left|right] [--assist cup|egg|can] [--backend sim|serial|pca9685|dry] [--dev /dev/ttyACM0] [--auto-profile] [--present]
# Default: mock stream + MuJoCo-free dry backend. --real = do not start mock (Rokoko Studio sends to UDP 14043).
MOCK=1; BACKEND=dry; DEV=""; ASSIST=""; IN=14043; HAND=right; AUTO_PROFILE=0
DASHBOARD_ARGS=()
while [ $# -gt 0 ]; do case "$1" in
  --auto-profile) AUTO_PROFILE=1;;
  --present) DASHBOARD_ARGS+=(--present);;
  --real) MOCK=0;; --bimanual) IN=14053;; --hand) HAND="$2"; shift;; --assist) ASSIST="--assist $2"; shift;; --backend) BACKEND="$2"; shift;; --dev) DEV="--dev $2"; shift;;
esac; shift; done
if [ "$AUTO_PROFILE" = 1 ]; then
  if [ ! -f "${FRAME:-}" ] || [ ! -r "$FRAME" ]; then
    echo "--auto-profile requires FRAME to point to a readable image." >&2
    exit 2
  fi
  case "$FRAME" in /*) ;; *) FRAME="$PWD/$FRAME";; esac
fi
cd "$(dirname "$0")/.." || exit 1
PY=${PYTHON:-$(command -v python3 || command -v python)}   # Windows Git Bash has no python3
# A single listener owns 14070 and relays profile changes to both local consumers.
PROFILE_IN=14070; SIM_PROFILE=14071; HAND_PROFILE=14072
trap 'kill $(jobs -p) 2>/dev/null' EXIT INT TERM
"$PY" demo/fanout.py --in "$IN" --out 14044 14045 14046 &
"$PY" demo/fanout.py --loopback --in "$PROFILE_IN" --out "$SIM_PROFILE" "$HAND_PROFILE" &
"$PY" -m robot.sim_server --port 14046 --obj egg --hand "$HAND" --profile-port "$SIM_PROFILE" $ASSIST &
"$PY" -m robot.run_udp --backend "$BACKEND" --port 14045 --hand "$HAND" --profile-port "$HAND_PROFILE" $ASSIST $DEV &
if [ "$MOCK" = 1 ]; then
  "$PY" Rokoko/src/mock_stream.py &
fi
if [ "$AUTO_PROFILE" = 1 ]; then
  (
    # UDP drops a one-shot packet if it reaches a consumer before bind().
    "$PY" - "$PROFILE_IN" "$SIM_PROFILE" "$HAND_PROFILE" <<'PY' || exit 1
import errno
import socket
import sys
import time

pending = {int(port) for port in sys.argv[1:]}
deadline = time.monotonic() + 10
while pending and time.monotonic() < deadline:
    for port in pending.copy():
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                if exc.errno != errno.EADDRINUSE:
                    raise
                pending.remove(port)
    if pending:
        time.sleep(0.05)
if pending:
    sys.exit(f"Auto-profile skipped: UDP listeners did not start on {sorted(pending)}")
PY
    picker=(-m ai.pick_profile --image "$FRAME")
    if [ -n "${HX:-}" ] && [ -n "${HY:-}" ] && [ -n "${HZ:-}" ]; then
      picker+=(--hand-in-head "$HX" "$HY" "$HZ")
    fi
    exec "$PY" "${picker[@]}"
  ) &
fi
sleep 0.5
"$PY" demo/dashboard.py --port 14044 "${DASHBOARD_ARGS[@]}"
