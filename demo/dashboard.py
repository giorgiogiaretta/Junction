"""Live demo dashboard: finger values, gesture label, latency/rate.
Listens UDP JSON: single hand {"fingers":[5],"hand":"left|right","t":..} (14043) or bimanual {"left":[5]|null,"right":[5]|null,"t":..} (14053).
Latency = now - t if "t" present (same-machine or synced clocks), else shows inter-arrival gap.
Run: python demo/dashboard.py [--port 14043]   (mock: python Rokoko/src/mock_stream.py)
"""
import argparse, json, socket, sys, time, collections
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
from robot.parse import parse_hands, parse_state
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets

NAMES = ["thumb", "index", "middle", "ring", "pinky"]


def gesture(f, th=0.6):
    c = [x > th for x in f]  # closed?
    if not any(c): return "open hand"
    if all(c): return "fist"
    if c == [True, False, True, True, True]: return "point"
    if c == [True, False, False, True, True]: return "peace"
    if c == [False, True, True, True, True]: return "thumbs up"
    return "other"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=14043)
    ap.add_argument("--sim-port", type=int, default=14060, help="state JSON from robot/sim_server.py (egg force, button, latency)")
    ap.add_argument("--break-force", type=float, default=3.0)
    a, _ = ap.parse_known_args()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", a.port)); sock.setblocking(False)
    simsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); simsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    simsock.bind(("0.0.0.0", a.sim_port)); simsock.setblocking(False)

    app = pg.mkQApp("Junction glove demo")
    win = pg.GraphicsLayoutWidget(title="Rokoko glove -> robot hand"); win.resize(900, 700); win.show()
    lbl = win.addLabel("waiting for stream...", row=0, col=0, colspan=2, size="28pt")
    bars_p = win.addPlot(row=1, col=0, title="Fingers (0 open - 1 closed)")
    bars_p.setYRange(0, 1); bars_p.getAxis("bottom").setTicks([list(enumerate(NAMES))])
    bars = {"left": pg.BarGraphItem(x=[i - 0.2 for i in range(5)], height=[0] * 5, width=0.35, brush="m"),
            "right": pg.BarGraphItem(x=[i + 0.2 for i in range(5)], height=[0] * 5, width=0.35, brush="c")}
    for b in bars.values(): bars_p.addItem(b)
    lat_p = win.addPlot(row=1, col=1, title="Latency / frame gap (ms)")
    lat_curve = lat_p.plot(pen="y")
    hist_p = win.addPlot(row=2, col=0, colspan=2, title="Finger history")
    curves = {h: [hist_p.plot(pen=pg.mkPen(pg.intColor(i, 5), style=QtCore.Qt.PenStyle.SolidLine if h == "right" else QtCore.Qt.PenStyle.DashLine),
                              name="%s %s" % (h[0].upper(), n)) for i, n in enumerate(NAMES)] for h in ("left", "right")}
    hist_p.setYRange(0, 1); hist_p.addLegend()
    force_title = "Simulated contact force (N)"
    force_p = win.addPlot(row=3, col=0, title=force_title)
    force_p.setYRange(0, a.break_force * 2); force_p.setXRange(-0.5, 1.5); force_p.hideAxis("bottom")
    force_bar = pg.BarGraphItem(x=[0], height=[0], width=0.6, brush="g"); force_p.addItem(force_bar)
    peak_bar = pg.BarGraphItem(x=[1], height=[0], width=0.6, brush="y"); force_p.addItem(peak_bar)
    force_p.addItem(pg.InfiniteLine(pos=a.break_force, angle=0, pen=pg.mkPen("r", width=2)))
    status = win.addLabel("HANDOFF: -", row=3, col=1, size="22pt")
    profile = win.addLabel(row=4, col=0, colspan=2, size="16pt")
    def _key(e):  # RGMP exposes no Smartgloves II button: press H (or Space) to toggle the HandOff state by hand
        if e.key() in (QtCore.Qt.Key.Key_H, QtCore.Qt.Key.Key_Space): st["manual"] = not st["manual"]
    win.keyPressEvent = _key

    N = 300
    hist = {h: [collections.deque([0.0] * N, maxlen=N) for _ in range(5)] for h in ("left", "right")}
    lat = collections.deque([0.0] * N, maxlen=N)
    st = {"f": {"left": None, "right": None}, "n": 0, "t0": time.time(), "rate": 0, "last": None, "lat": 0.0, "kind": "gap", "button": False, "manual": False, "sim": None, "sim_last": None}

    def tick():
        got = False
        while True:
            try: data, _ = sock.recvfrom(1 << 16)
            except BlockingIOError: break
            now = time.time()
            try: m = json.loads(data.decode()); hands = parse_hands(m)
            except Exception: continue
            if hands["left"] is None and hands["right"] is None: continue
            got = True; st["n"] += 1
            if "fingers" in m:
                try: st["button"] = parse_state(m)["button"]
                except Exception: pass
            for h, f in hands.items():
                if f is not None:
                    st["f"][h] = f
                    for i in range(5): hist[h][i].append(f[i])
            if "t" in m: st["lat"] = (now - float(m["t"])) * 1000; st["kind"] = "latency"
            elif st["last"] is not None: st["lat"] = (now - st["last"]) * 1000; st["kind"] = "frame gap"
            st["last"] = now
            lat.append(st["lat"])
        while True:
            try: d2, _ = simsock.recvfrom(1 << 16)
            except BlockingIOError: break
            try: st["sim"] = json.loads(d2.decode()); st["sim_last"] = time.time(); st["button"] = bool(st["sim"].get("button", st["button"]))
            except Exception: pass
        now = time.time()
        if now - st["t0"] >= 1: st["rate"] = st["n"] / (now - st["t0"]); st["n"] = 0; st["t0"] = now
        if got:
            for h in ("left", "right"):
                bars[h].setOpts(height=st["f"][h] or [0] * 5)
                for c, d in zip(curves[h], hist[h]): c.setData(np.array(d))
            lat_curve.setData(np.array(lat))
        live = st["last"] is not None and time.time() - st["last"] < 1.0
        arr = np.array(list(lat)[-200:]) if st["last"] is not None else np.zeros(1)
        p50, p95 = np.percentile(arr, 50), np.percentile(arr, 95)
        gs = "  ".join("%s: %s" % (h[0].upper(), gesture(st["f"][h]).upper()) for h in ("left", "right") if st["f"][h]) or "-"
        lbl.setText("%s %s | %s | %s p50 %.1f / p95 %.1f ms | %.0f fps" % ("LIVE" if live else "NO STREAM", "●" if live else "○", gs, st["kind"], p50, p95, st["rate"]))
        sim = st["sim"] if st["sim_last"] and time.time() - st["sim_last"] < 1.0 else None
        if sim:
            force_bar.setOpts(height=[sim["force"]], brush="r" if sim.get("broken") else "g")
            peak_bar.setOpts(height=[sim["peak_force"]])
            force_p.setTitle("%s · %s: %s" % (force_title, sim.get("obj", "object"), "BROKEN" if sim.get("broken") else "intact"))
        else:
            force_bar.setOpts(height=[0]); peak_bar.setOpts(height=[0])
            force_p.setTitle(force_title)
        if sim and "profile" in sim and "cap" in sim:
            profile.setText("Simulation · Force Cushion: %s · Closure cap: %.0f%%" % (sim["profile"], sim["cap"] * 100))
        else:
            profile.setText("Simulation · Waiting for Force Cushion telemetry")
        status.setText("HANDOFF: %s" % ("HUMAN in control" if (st["button"] or st["manual"]) else "robot / auto (H = take over)"))

    t = QtCore.QTimer(); t.timeout.connect(tick); t.start(16)
    if "--selftest" in sys.argv: QtCore.QTimer.singleShot(1500, app.quit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
