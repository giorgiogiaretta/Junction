"""Runtime Force Cushion profile switching: pick_profile --set -> UDP -> sim_server (cap changes from 1.0 to 0.5)."""
import json, socket, subprocess, sys, time, pathlib
ROOT = pathlib.Path(__file__).parents[1]


def _port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def test_profile_switch_changes_cap():
    inp, out, prof = _port(), _port(), _port()
    r = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); r.bind(("127.0.0.1", out)); r.setblocking(False)
    srv = subprocess.Popen([sys.executable, "-m", "robot.sim_server", "--obj", "egg", "--port", str(inp), "--out", str(out), "--profile-port", str(prof)], cwd=ROOT)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    def feed(n=60):
        last = None
        for _ in range(n):
            s.sendto(json.dumps({"t": time.time(), "hand": "right", "fingers": [1] * 5}).encode(), ("127.0.0.1", inp)); time.sleep(0.01)
            try:
                while True: last = json.loads(r.recv(4096))
            except BlockingIOError: pass
        return last
    try:
        time.sleep(2.0); a = feed()
        subprocess.run([sys.executable, "-m", "ai.pick_profile", "--set", "egg", "--port", str(prof)], cwd=ROOT, check=True, capture_output=True, timeout=30)
        time.sleep(0.3); b = feed()
        assert a["profile"] == "none" and a["cap"] == 1.0 and b["profile"] == "egg" and b["cap"] == 0.5, (a, b)
    finally:
        srv.terminate(); srv.wait(timeout=5)
