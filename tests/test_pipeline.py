"""Headless integration tests (no GUI/hardware): retarget, hands, RGMP client vs mock server, UDP fan-out chain."""
import json, socket, struct, subprocess, sys, time, pathlib
ROOT = pathlib.Path(__file__).parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "Rokoko" / "src"))

def test_retarget_ranges():
    from robot.retarget import to_inspire
    o = to_inspire([0, 0, 0, 0, 0]); c = to_inspire([1, 1, 1, 1, 1])
    assert len(o) == 6 and all(0 <= v <= 1000 for v in o + c) and o != c
    capped = to_inspire([1, 1, 1, 1, 1], close_cap=0.5)
    assert all(a >= b for a, b in zip(capped[:4], c[:4]))  # 1000 = open: cap keeps hand more open

def test_dry_and_inspire_dry():
    from robot.hand import make_hand
    for kind in ("dry", "inspire"):
        h = make_hand(kind); h.set_fingers([0.2, 0.4, 0.6, 0.8, 1.0]); h.close()

def test_sim_hand():
    from robot.hand import make_hand
    h = make_hand("sim"); h.set_fingers([1, 1, 1, 1, 1]); h.set_fingers([0, 0, 0, 0, 0]); assert h.angles() is not None

def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def test_fanout_chain():
    inp, o1, o2 = _free_port(), _free_port(), _free_port()
    r1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); r1.bind(("127.0.0.1", o1)); r1.settimeout(5)
    r2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); r2.bind(("127.0.0.1", o2)); r2.settimeout(5)
    p = subprocess.Popen([sys.executable, str(ROOT / "demo" / "fanout.py"), "--in", str(inp), "--out", str(o1), str(o2)])
    try:
        time.sleep(0.8); s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for _ in range(5): s.sendto(json.dumps({"fingers": [.1, .2, .3, .4, .5]}).encode(), ("127.0.0.1", inp)); time.sleep(0.05)
        assert json.loads(r1.recv(4096))["fingers"][4] == 0.5 and json.loads(r2.recv(4096))["fingers"][0] == 0.1
    finally: p.kill()

def test_rgmp_client_vs_mock():
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); u.bind(("127.0.0.1", 0)); up = u.getsockname()[1]; u.settimeout(15)
    srv = subprocess.Popen([sys.executable, str(ROOT / "Rokoko" / "src" / "mock_rgmp_server.py")]); time.sleep(1.5)
    cli = subprocess.Popen([sys.executable, str(ROOT / "Rokoko" / "src" / "rgmp_client.py"), "--calibrate", "2", "--udp-port", str(up)], stderr=subprocess.DEVNULL)
    try:
        f = json.loads(u.recv(4096))["fingers"]; assert len(f) == 5 and all(0 <= x <= 1 for x in f)
    finally: cli.kill(); srv.kill()
