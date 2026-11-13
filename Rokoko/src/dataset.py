"""Load recorded data/*.jsonl (from listen.py) into numpy windows. Optional labels via --label in record_labeled.py."""
import json, sys, pathlib
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from parser import parse

def load(path):
    t, x = [], []
    for line in open(path):
        r = json.loads(line); f = parse(r["frame"])
        if f is not None: t.append(r["t"]); x.append(f)
    return np.array(t), np.array(x, dtype=np.float32)

def windows(x, size=30, step=10):
    return np.stack([x[i:i + size] for i in range(0, len(x) - size + 1, step)]) if len(x) >= size else np.empty((0, size, 5))

def replay(path, speed=1.0, send=None):
    import time
    t, x = load(path)
    for i in range(len(x)):
        if i: time.sleep(max(0, (t[i] - t[i - 1]) / speed))
        send(x[i].tolist()) if send else print(x[i].round(2))

if __name__ == "__main__":
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    replay(sys.argv[1], send=lambda f: s.sendto(json.dumps({"fingers": f}).encode(), ("127.0.0.1", 14043)))
