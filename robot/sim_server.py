"""Run the MuJoCo grasp scene from a live hand_state UDP stream and publish its state for the dashboard.
In: UDP JSON hand_state (single hand {"fingers":[5],"t":..,"wrist_position"?,"button_pressed"?}) on --port (default 14046, fed by demo/fanout.py).
Out: UDP JSON {obj,force,peak_force,broken,lifted,latency_ms,lat_p50,lat_p95,cap,button} to 127.0.0.1:--out (default 14060).
Usage: python -m robot.sim_server --obj egg --assist egg   (no wrist_position in the stream -> mock wrist path; reset with --reset-after N s idle)
"""
import argparse, json, socket, time
from robot.pipeline import Pipeline

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=14046); ap.add_argument("--out", type=int, default=14060)
ap.add_argument("--obj", default="egg", choices=["cube", "egg"]); ap.add_argument("--assist", choices=["cup", "egg", "can"])
ap.add_argument("--hand", choices=["left", "right"], default="right")
a = ap.parse_args()
p = Pipeline(a.obj, a.assist)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind(("0.0.0.0", a.port)); s.settimeout(1.0)
o = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
while True:
    try:
        m = json.loads(s.recv(1 << 16).decode())
    except socket.timeout:
        continue
    except ValueError:
        continue
    if "left" in m or "right" in m:  # bimanual packet -> pick one glove
        f = m.get(a.hand)
        if f is None: continue
        m = {"t": m.get("t"), "fingers": f, "hand": a.hand}
    st = p.process(m)
    if st is None: continue
    lat = p.latency_stats()
    out = {"obj": a.obj, "force": st["force"], "peak_force": st["peak_force"], "broken": st["broken"], "lifted": st["lifted"],
           "latency_ms": st["latency_ms"], "lat_p50": lat["p50"], "lat_p95": lat["p95"], "cap": st["cap"], "button": st["button"]}
    o.sendto(json.dumps(out).encode(), ("127.0.0.1", a.out))
