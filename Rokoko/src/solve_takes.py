"""Run recorded raw takes through the Rokoko SDK hand solver (rkk-hand-solver, 26-joint skeleton, local joint rotations) offline.
python Rokoko/src/solve_takes.py [take numbers...]   -> data/solved/take_NN.npz: per hand t, joint names, rot_angle (N,J) rad (rotation magnitude of each
local joint quaternion). Uses ports 12299 (replay) and 12277 (solver). Needs the SDK installed+activated. Fast replay (x10).
"""
import json, math, os, socket, struct, subprocess, sys, time
import numpy as np

SDK = os.path.join(os.environ["LOCALAPPDATA"], "Rokoko Device SDK", "bin", "rkk-hand-solver.exe")
os.makedirs("data/solved", exist_ok=True)
takes = [json.loads(l) for l in open("data/raw/takes.jsonl")]
want = {int(a) for a in sys.argv[1:]} or {t["take"] for t in takes}

def rx(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c: raise ConnectionError
        b += c
    return b

def solve(t):
    rp = subprocess.Popen([sys.executable, "Rokoko/src/replay_rgmp.py", t["file"], "--port", "12299", "--speed", "4", "--delay", "3"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    sv = subprocess.Popen([SDK, "--no-driver", "--rgmp-addr", "127.0.0.1:12299", "--listen", "127.0.0.1:12277", "--emit", "local"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.4)
    out = {}; names = {}
    try:
        s = socket.create_connection(("127.0.0.1", 12277)); s.settimeout(4); lay = {}
        while True:
            typ, ln = struct.unpack("<II", rx(s, 8)); p = rx(s, ln)
            if typ == 1:
                sd = json.loads(p); d = sd["device_id"]; hand = sd["device_info"]["hand"]
                g = next(g for g in sd["groups"] if g["name"] == "joints_local")
                lay[d] = (hand, [(st["target_frame"], st["data_type"]) for st in g["streams"]], sd["groups"].index(g))
                names[hand] = [f for f, dt in lay[d][1] if dt == "FLOAT[4]"]; out[hand] = {"t": [], "a": []}
            elif typ == 2:
                d, gid, ts = struct.unpack_from("<IIQ", p, 0)
                if d not in lay or gid != lay[d][2]: continue
                hand, streams, _ = lay[d]; off, ang = 16, []
                for f, dt in streams:
                    n = int(dt.split("[")[1].rstrip("]")) if "[" in dt else 1
                    v = struct.unpack_from("<%df" % n, p, off); off += 4 * n
                    if dt == "FLOAT[4]": ang.append(2 * math.acos(max(-1.0, min(1.0, abs(v[3])))))
                out[hand]["t"].append(ts / 1e6); out[hand]["a"].append(ang)
    except (socket.timeout, ConnectionError): pass
    finally:
        for x in (sv, rp): x.kill()
    for hand, o in out.items():
        if len(o["t"]) > 20:
            np.savez_compressed(f"data/solved/take_{t['take']:02d}_{hand}.npz", t=np.array(o["t"]), joints=np.array(names[hand]), rot_angle=np.array(o["a"], dtype=np.float32))
    return {h: len(o["t"]) for h, o in out.items()}

for t in takes:
    if t["take"] in want:
        t0 = time.time(); print("take", t["take"], t["series"], solve(t), f"{time.time()-t0:.0f}s", flush=True)
