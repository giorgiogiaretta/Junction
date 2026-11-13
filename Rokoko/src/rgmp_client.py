"""RGMP client for the Rokoko Device SDK driver (TCP, default 127.0.0.1:12276).
Spec: https://sdk.rokoko.com/reference/rgmp/  -> frame = u32 type, u32 len, payload (little endian).
 type 1 = stream definition (UTF-8 JSON), 2 = data frame (16B header: u32 device, u32 group, u64 ts_us + values), 3 = disconnect.
Run: rokoko-sdk --auto-stream-usb   (driver)   then   python src/rgmp_client.py [--jsonl data/x.jsonl] [--udp-port 14043]
ASSUMPTIONS to verify on real hardware: group_id = index in definition "groups"; transform layout (see quat()).
Finger values are CALIBRATED: hold hand open ~3 s, then closed ~3 s (--calibrate) so layout details don't matter.
"""
import argparse, json, math, socket, struct, sys, time

SIZES = {"INT32": 4, "UINT32": 4, "FLOAT": 4, "INT64": 8, "UINT64": 8, "DOUBLE": 8}
FMT = {"INT32": "i", "UINT32": "I", "FLOAT": "f", "INT64": "q", "UINT64": "Q", "DOUBLE": "d"}
FINGERS = ["thumb", "index", "middle", "ring", "little"]

def parse_type(t):  # "FLOAT[4,4]" -> ("FLOAT", 16)
    if "[" not in t: return t, 1
    base, dims = t.split("[", 1)
    n = 1
    for d in dims.rstrip("]").split(","): n *= int(d)
    return base, n

def build_layout(sd):
    groups = []
    for g in sd["groups"]:
        fmt, items = "<", []
        for s in g["streams"]:
            base, n = parse_type(s["data_type"])
            fmt += FMT[base] * n; items.append((s, n))
        groups.append((g["name"], struct.Struct(fmt), items))
    return groups

def decode(layout, payload):
    dev, gid, ts = struct.unpack_from("<IIQ", payload, 0)
    name, st, items = layout[gid]
    vals = st.unpack_from(payload, 16); out, i = [], 0
    for s, n in items:
        out.append((s, list(vals[i:i + n]))); i += n
    return dev, name, ts, out

def quat(v):
    """Rotation quaternion (x,y,z,w) from a TRANSFORM value. Assumed layout: 7 floats = pos(3)+quat(4), or 4 = quat."""
    return v[-4:] if len(v) >= 4 else None

def qmul_conj(a, b):  # a * conj(b)
    ax, ay, az, aw = a; bx, by, bz, bw = [-b[0], -b[1], -b[2], b[3]]
    return (aw*bx + ax*bw + ay*bz - az*by, aw*by - ax*bz + ay*bw + az*bx, aw*bz + ax*by - ay*bx + az*bw, aw*bw - ax*bx - ay*by - az*bz)

def angle_of(q):
    return 2 * math.acos(max(-1.0, min(1.0, abs(q[3]))))

def recv_exact(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c: raise ConnectionError("closed")
        b += c
    return b

def run(a):
    s = socket.create_connection((a.host, a.port)); udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    out = open(a.jsonl, "a") if a.jsonl else None
    layout, lo, hi, t_start = None, [9.0] * 5, [0.0] * 5, time.time()
    while True:
        typ, ln = struct.unpack("<II", recv_exact(s, 8)); p = recv_exact(s, ln)
        if typ == 1:
            sd = json.loads(p.decode("utf-8")); layout = build_layout(sd)
            print("stream def:", sd.get("device_type"), sd.get("device_info"), [g["name"] for g in sd["groups"]], file=sys.stderr)
        elif typ == 2 and layout:
            dev, name, ts, items = decode(layout, p)
            if name != "default": continue
            q = {s_["target_frame"]: quat(v) for s_, v in items if s_["measure_type"] == "TRANSFORM" and s_["target_frame"].endswith("finger_sensor")}
            ang = []
            for f in FINGERS:
                k = f + "_finger_sensor"
                ang.append(angle_of(q[k]) if k in q and q[k] else 0.0)
            if out: out.write(json.dumps({"ts_us": ts, "dev": dev, "angles": ang}) + "\n")
            el = time.time() - t_start
            if el < a.calibrate:        # phase 1: open+closed sweep to learn per-finger range
                lo = [min(x, y) for x, y in zip(lo, ang)]; hi = [max(x, y) for x, y in zip(hi, ang)]
                continue
            f01 = [round(min(1, max(0, (x - l) / (h - l + 1e-6))), 3) for x, l, h in zip(ang, lo, hi)]
            udp.sendto(json.dumps({"fingers": f01, "t": time.time(), "src": "rokoko"}).encode(), ("127.0.0.1", a.udp_port))
        elif typ == 3:
            print("device disconnected", file=sys.stderr)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=12276)
    ap.add_argument("--udp-port", type=int, default=14043); ap.add_argument("--jsonl")
    ap.add_argument("--calibrate", type=float, default=8.0, help="seconds: open and close your hand repeatedly")
    run(ap.parse_args())
