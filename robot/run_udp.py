"""Drive a hand from UDP JSON {"fingers":[5]} (mock_stream/forward format; also accepts port 14043).
Usage: python -m robot.run_udp --backend sim|serial|pca9685|dry [--port 14043] [--dev /dev/ttyACM0]
"""
import argparse, json, socket
from robot.hand import make_hand

ap = argparse.ArgumentParser()
ap.add_argument("--backend", default="dry"); ap.add_argument("--port", type=int, default=14043)
ap.add_argument("--dev"); ap.add_argument("--host", default="192.168.123.210")
ap.add_argument("--live", action="store_true", help="inspire: really send (default dry)")
ap.add_argument("--close-cap", type=float, default=1.0); a = ap.parse_args()
kw = {"port": a.dev} if a.backend == "serial" else {}
if a.backend == "inspire": kw = {"host": a.host, "dry": not a.live, "close_cap": a.close_cap}
h = make_hand(a.backend, **kw)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("0.0.0.0", a.port))
while True:
    try:
        h.set_fingers(json.loads(s.recv(1 << 16).decode())["fingers"])
    except (KeyError, ValueError):
        pass
