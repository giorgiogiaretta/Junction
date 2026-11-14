"""UDP fan-out: receive glove stream on --in (default 14043), resend to several ports.
Usage: python demo/fanout.py --out 14044 14045
"""
import argparse, socket
ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="inp", type=int, default=14043)
ap.add_argument("--out", type=int, nargs="+", default=[14044, 14045])
ap.add_argument("--loopback", action="store_true", help="accept packets from this machine only")
a = ap.parse_args()
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("127.0.0.1" if a.loopback else "0.0.0.0", a.inp))
o = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
while True:
    d = s.recv(1 << 16)
    for p in a.out: o.sendto(d, ("127.0.0.1", p))
