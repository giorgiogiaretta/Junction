"""Record/replay raw RGMP streams. Replay serves the bytes like the real Rokoko server so rgmp_client.py runs unchanged.
File format: repeated [f64 t_offset_s][u32 len][bytes] chunks (bytes = exact data as received)."""
import argparse, socket, struct, time

H = struct.Struct("<dI")


def record(a):
    s = socket.create_connection((a.host, a.port)); t0 = time.time(); n = 0
    with open(a.record, "wb") as f:
        try:
            while a.seconds <= 0 or time.time() - t0 < a.seconds:
                b = s.recv(65536)
                if not b: break
                f.write(H.pack(time.time() - t0, len(b)) + b); n += 1
        except KeyboardInterrupt: pass
    print(f"recorded {n} chunks to {a.record}")


def chunks(path):
    with open(path, "rb") as f:
        while len(h := f.read(H.size)) == H.size:
            t, n = H.unpack(h); yield t, f.read(n)


def replay(a):
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); srv.bind((a.host, a.port)); srv.listen(1)
    print(f"replaying {a.path} on {a.host}:{a.port}")
    while True:
        c, _ = srv.accept(); t0 = time.time()
        try:
            for t, b in chunks(a.path):
                d = t / a.speed - (time.time() - t0)
                if d > 0: time.sleep(d)
                c.sendall(b)
        except (BrokenPipeError, ConnectionError): pass
        c.close()
        if not a.loop: break


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("path", nargs="?")
    ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=12276)
    ap.add_argument("--speed", type=float, default=1.0); ap.add_argument("--loop", action="store_true")
    ap.add_argument("--record"); ap.add_argument("--seconds", type=float, default=0)
    a = ap.parse_args()
    record(a) if a.record else replay(a)
