"""Live demo dashboard: finger values, gesture label, latency/rate.
Listens UDP JSON {"fingers":[5 floats 0..1], optional "t": sender time.time()}.
Latency = now - t if "t" present (same-machine or synced clocks), else shows inter-arrival gap.
Run: python demo/dashboard.py [--port 14043]   (mock: python Rokoko/src/mock_stream.py)
"""
import argparse, json, socket, sys, time, collections
import numpy as np
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
    a, _ = ap.parse_known_args()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", a.port)); sock.setblocking(False)

    app = pg.mkQApp("Junction glove demo")
    win = pg.GraphicsLayoutWidget(title="Rokoko glove -> robot hand"); win.resize(900, 700); win.show()
    lbl = win.addLabel("waiting for stream...", row=0, col=0, colspan=2, size="28pt")
    bars_p = win.addPlot(row=1, col=0, title="Fingers (0 open - 1 closed)")
    bars_p.setYRange(0, 1); bars_p.getAxis("bottom").setTicks([list(enumerate(NAMES))])
    bars = pg.BarGraphItem(x=list(range(5)), height=[0] * 5, width=0.6, brush="c"); bars_p.addItem(bars)
    lat_p = win.addPlot(row=1, col=1, title="Latency / frame gap (ms)")
    lat_curve = lat_p.plot(pen="y")
    hist_p = win.addPlot(row=2, col=0, colspan=2, title="Finger history")
    curves = [hist_p.plot(pen=pg.intColor(i, 5), name=n) for i, n in enumerate(NAMES)]
    hist_p.setYRange(0, 1); hist_p.addLegend()

    N = 300
    hist = [collections.deque([0.0] * N, maxlen=N) for _ in range(5)]
    lat = collections.deque([0.0] * N, maxlen=N)
    st = {"f": [0] * 5, "n": 0, "t0": time.time(), "rate": 0, "last": None, "lat": 0.0, "kind": "gap"}

    def tick():
        got = False
        while True:
            try: data, _ = sock.recvfrom(1 << 16)
            except BlockingIOError: break
            now = time.time()
            try: m = json.loads(data.decode()); f = [float(x) for x in m["fingers"][:5]]
            except Exception: continue
            if len(f) < 5: continue
            got = True; st["f"] = f; st["n"] += 1
            if "t" in m: st["lat"] = (now - float(m["t"])) * 1000; st["kind"] = "latency"
            elif st["last"] is not None: st["lat"] = (now - st["last"]) * 1000; st["kind"] = "frame gap"
            st["last"] = now
            for i in range(5): hist[i].append(f[i])
            lat.append(st["lat"])
        now = time.time()
        if now - st["t0"] >= 1: st["rate"] = st["n"] / (now - st["t0"]); st["n"] = 0; st["t0"] = now
        if got:
            bars.setOpts(height=st["f"])
            for c, h in zip(curves, hist): c.setData(np.array(h))
            lat_curve.setData(np.array(lat))
            lbl.setText("%s   |   %.1f ms %s   |   %.0f fps" % (gesture(st["f"]).upper(), st["lat"], st["kind"], st["rate"]))

    t = QtCore.QTimer(); t.timeout.connect(tick); t.start(16)
    if "--selftest" in sys.argv: QtCore.QTimer.singleShot(1500, app.quit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
