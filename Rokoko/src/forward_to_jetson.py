"""Laptop: take glove frames (or mock) and forward finger values to the Jetson over UDP.
Usage: python src/forward_to_jetson.py --jetson 192.168.x.y [--port 5005] [--mock]
TODO: replace extract_fingers() once a real Rokoko frame is inspected (listen.py --show).
"""
import argparse, json, math, socket, time

ap = argparse.ArgumentParser()
ap.add_argument("--jetson", required=True)
ap.add_argument("--port", type=int, default=5005)
ap.add_argument("--rokoko-port", type=int, default=14043)
ap.add_argument("--mock", action="store_true")
a = ap.parse_args()

def extract_fingers(frame):
    raise NotImplementedError("map real Rokoko JSON -> 5 floats 0..1")

out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
if a.mock:
    t0 = time.time()
    while True:
        t = time.time() - t0
        f = [0.5 + 0.5 * math.sin(2 * t + i) for i in range(5)]
        out.sendto(json.dumps({"fingers": f, "t": time.time()}).encode(), (a.jetson, a.port)); time.sleep(1 / 60)
inp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); inp.bind(("0.0.0.0", a.rokoko_port))
while True:
    data, _ = inp.recvfrom(1 << 20)
    f = extract_fingers(json.loads(data.decode("ascii", "ignore")))
    out.sendto(json.dumps({"fingers": f, "t": time.time()}).encode(), (a.jetson, a.port))
