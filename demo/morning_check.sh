#!/usr/bin/env bash
# Readiness table for the morning. Usage: [INSPIRE_HOST=192.168.x.y] demo/morning_check.sh   (keys must be exported in this shell)
cd "$(dirname "$0")/.."; PY=${PYTHON:-python3}
ok()  { printf "  [ OK ] %s\n" "$1"; }
bad() { printf "  [MISS] %s\n" "$1"; }
echo "== repo"; git pull -q --rebase 2>&1 | tail -1; git log --oneline -1
echo "== tests"; if $PY -m pytest tests -q > /tmp/morning_pytest.txt 2>&1; then ok "pytest: $(tail -1 /tmp/morning_pytest.txt)"; else bad "pytest FAILED, see /tmp/morning_pytest.txt"; fi
echo "== keys (presence only, never printed)"
[ -n "$VERDA_INFERENCE_KEY" ] && ok "VERDA_INFERENCE_KEY (Nemotron)" || bad "VERDA_INFERENCE_KEY"
[ -n "$GEMINI_API_KEY$GOOGLE_API_KEY" ] && ok "Gemini key" || bad "GEMINI_API_KEY / GOOGLE_API_KEY (Gemini not wired yet: set LLM_BASE_URL/LLM_MODEL/LLM_API_KEY to try)"
echo "== Nemotron ping"
if [ -n "$VERDA_INFERENCE_KEY$NVIDIA_API_KEY" ]; then
  $PY - <<'PY' && ok "Nemotron answers" || bad "Nemotron did not answer"
import sys, time
from ai.llm import ChatClient
t = time.time(); m = ChatClient(timeout=30).chat([{"role": "user", "content": "Reply with: pong"}], max_tokens=300)
print("    %.1fs -> %r" % (time.time() - t, (m.get("content") or "")[:20])); sys.exit(0 if m.get("content") else 1)
PY
else bad "skipped (no key)"; fi
echo "== Inspire hand"
if [ -n "$INSPIRE_HOST" ]; then ping -c1 -t2 "$INSPIRE_HOST" > /dev/null 2>&1 && ok "ping $INSPIRE_HOST" || bad "no ping to $INSPIRE_HOST"
else bad "INSPIRE_HOST not set (ask Aalto: IP, port, registers ANGLE_SET/FORCE_ACT)"; fi
echo "== cameras (opencv indices 0-3)"
$PY - <<'PY' 2>/dev/null || bad "opencv not installed (pip install opencv-python)"
import cv2
found = []
for i in range(4):
    c = cv2.VideoCapture(i); ok, _ = c.read(); c.release()
    if ok: found.append(i)
print("  [ OK ] camera indices with a frame: %s" % found if found else "  [MISS] no camera frame on indices 0-3")
PY
echo "== loop agent"; command -v timeout > /dev/null && ok "timeout available" || bad "timeout missing: brew install coreutils; export PATH=/opt/homebrew/opt/coreutils/libexec/gnubin:\$PATH"
