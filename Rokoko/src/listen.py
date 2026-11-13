"""Listen to Rokoko Studio Live UDP stream and save raw frames to data/*.jsonl.
Studio: Livestream > Custom forward > UDP, target 127.0.0.1:14043, format JSON v3 (not Lz4).
Usage: python src/listen.py [--port 14043] [--out data/session.jsonl] [--show]
Frame structure is NOT assumed: inspect one frame with --show first.
"""
import argparse, json, socket, time

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=14043)
ap.add_argument("--out", default=f"data/session_{int(time.time())}.jsonl")
ap.add_argument("--show", action="store_true", help="print first frame and exit")
a = ap.parse_args()

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("0.0.0.0", a.port))
print(f"listening on UDP {a.port} ...")
n = 0
f = None if a.show else open(a.out, "w")
while True:
    data, _ = s.recvfrom(1 << 20)
    try:
        frame = json.loads(data.decode("ascii", "ignore"))
    except json.JSONDecodeError:
        print("not plain JSON (Lz4? change format to JSON v3 in Studio)"); continue
    if a.show:
        print(json.dumps(frame, indent=1)[:4000]); break
    f.write(json.dumps({"t": time.time(), "frame": frame}) + "\n"); n += 1
    if n % 120 == 0: print(n, "frames"); f.flush()
