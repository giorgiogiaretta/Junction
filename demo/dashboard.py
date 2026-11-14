"""Live demo dashboard: finger values, gesture label, latency/rate.
Listens UDP JSON: single hand {"fingers":[5],"hand":"left|right","t":..} (14043) or bimanual {"left":[5]|null,"right":[5]|null,"t":..} (14053).
Latency = now - t if "t" present (same-machine or synced clocks), else shows inter-arrival gap.
Run: python demo/dashboard.py [--port 14043]   (mock: python Rokoko/src/mock_stream.py)
"""
import argparse, json, socket, sys, time, collections
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
from ai.llm import VERDA_URL
from robot.parse import parse_hands, parse_state
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
from PySide6 import QtNetwork

NAMES = ["thumb", "index", "middle", "ring", "pinky"]
BACKGROUND = "#090f17"
TEXT = "#f6faff"
GREEN = "#8ff3c9"
RED = "#ff9d9d"
AMBER = "#ffd18a"


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
    ap.add_argument("--present", action="store_true", help="start fullscreen for projection")
    ap.add_argument("--endpoint", default=os.environ.get("LLM_BASE_URL") or VERDA_URL,
                    help="OpenAI-compatible base URL for the unauthenticated /models check")
    a, _ = ap.parse_known_args()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", a.port)); sock.setblocking(False)
    simsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); simsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    simsock.bind(("0.0.0.0", a.sim_port)); simsock.setblocking(False)

    app = pg.mkQApp("Junction glove demo")
    pg.setConfigOptions(background=BACKGROUND, foreground=TEXT)
    win = QtWidgets.QWidget()
    win.setWindowTitle("HandOff · Live demo")
    win.resize(1280, 800)
    win.setStyleSheet(f"""
        QWidget {{ background: {BACKGROUND}; color: {TEXT}; font: 18pt sans-serif; }}
        QPushButton {{ background: #19293a; border: 2px solid #647c94; border-radius: 8px; padding: 8px 16px; }}
        QPushButton:focus {{ border-color: {TEXT}; }}
    """)
    layout = QtWidgets.QVBoxLayout(win)
    layout.setContentsMargins(24, 16, 24, 16)
    header = QtWidgets.QHBoxLayout()
    title = QtWidgets.QLabel("HandOff · Live demo")
    title.setStyleSheet("font-size: 28pt; font-weight: bold;")
    header.addWidget(title)
    header.addStretch()
    button = QtWidgets.QPushButton("Stato rete/endpoint · da verificare")
    button.setToolTip("GET /models senza credenziali. Verifica la raggiungibilità HTTP.")
    header.addWidget(button)
    layout.addLayout(header)
    network = QtNetwork.QNetworkAccessManager(win)

    def check_endpoint():
        url = QtCore.QUrl(a.endpoint.rstrip("/") + "/models")
        button.setEnabled(False)
        button.setStyleSheet("")
        button.setText("Stato rete/endpoint · verifica…")
        request = QtNetwork.QNetworkRequest(url)
        request.setAttribute(QtNetwork.QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QtNetwork.QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        reply = network.get(request)
        deadline = QtCore.QTimer(reply)
        deadline.setSingleShot(True)
        deadline.timeout.connect(reply.abort)
        deadline.start(4000)

        def show_result():
            deadline.stop()
            code = reply.attribute(QtNetwork.QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            reachable = code in (401, 403) or (
                code is not None and 200 <= code < 300
                and reply.error() == QtNetwork.QNetworkReply.NetworkError.NoError
            )
            if code in (401, 403):
                message = f"raggiungibile · HTTP {code} (accesso protetto)"
            elif reachable:
                message = f"raggiungibile · HTTP {code}"
            else:
                message = f"HTTP {code} · verifica fallita" if code else "non raggiungibile"
            button.setText(f"Stato rete/endpoint · {message}")
            button.setStyleSheet(f"color: {GREEN if reachable else RED};")
            button.setEnabled(True)
            reply.deleteLater()

        reply.finished.connect(show_result)

    button.clicked.connect(check_endpoint)
    plots = pg.GraphicsLayoutWidget()
    layout.addWidget(plots, stretch=1)
    lbl = plots.addLabel("Waiting for glove stream", row=0, col=0, colspan=2, size="20pt")
    profile = plots.addLabel("Simulation · Waiting for telemetry", row=1, col=0, colspan=2, size="24pt", color=TEXT)
    bars_p = plots.addPlot(row=2, col=1, title="Finger closure")
    bars_p.setYRange(0, 1); bars_p.getAxis("bottom").setTicks([list(enumerate(NAMES))])
    bars = {"left": pg.BarGraphItem(x=[i - 0.2 for i in range(5)], height=[0] * 5, width=0.35, brush="m"),
            "right": pg.BarGraphItem(x=[i + 0.2 for i in range(5)], height=[0] * 5, width=0.35, brush="c")}
    for b in bars.values(): bars_p.addItem(b)
    lat_p = plots.addPlot(row=3, col=0, title="Latency / frame gap (ms)")
    lat_curve = lat_p.plot(pen=pg.mkPen(AMBER, width=2))
    hist_p = plots.addPlot(row=3, col=1, title="Finger history")
    curves = {h: [hist_p.plot(pen=pg.mkPen(pg.intColor(i, 5), style=QtCore.Qt.PenStyle.SolidLine if h == "right" else QtCore.Qt.PenStyle.DashLine),
                              name="%s %s" % (h[0].upper(), n)) for i, n in enumerate(NAMES)] for h in ("left", "right")}
    hist_p.setYRange(0, 1); hist_p.addLegend()
    force_title = "Simulated contact force (N)"
    force_p = plots.addPlot(row=2, col=0, title=force_title)
    force_p.setYRange(0, a.break_force * 2); force_p.setXRange(-0.5, 1.5)
    force_p.getAxis("bottom").setTicks([[(0, "Current"), (1, "Peak")]])
    force_bar = pg.BarGraphItem(x=[0], height=[0], width=0.65, brush=GREEN); force_p.addItem(force_bar)
    peak_bar = pg.BarGraphItem(x=[1], height=[0], width=0.65, brush=AMBER); force_p.addItem(peak_bar)
    force_p.addItem(pg.InfiniteLine(pos=a.break_force, angle=0, pen=pg.mkPen(RED, width=3),
                                  label="Assumed threshold",
                                  labelOpts={"color": RED, "position": 0.05, "fill": BACKGROUND}))
    status = plots.addLabel("HANDOFF: -", row=4, col=0, colspan=2, size="20pt")
    plots.ci.layout.setRowStretchFactor(2, 3)
    plots.ci.layout.setRowStretchFactor(3, 1)
    for plot in (force_p, bars_p, lat_p, hist_p):
        for axis in ("left", "bottom"):
            plot.getAxis(axis).setTickFont(QtGui.QFont("sans-serif", 13))

    def toggle_handoff():
        st["manual"] = not st["manual"]

    QtGui.QShortcut(QtGui.QKeySequence("H"), win, activated=toggle_handoff)
    QtGui.QShortcut(QtGui.QKeySequence("Space"), plots, activated=toggle_handoff,
                    context=QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
    QtGui.QShortcut(QtGui.QKeySequence("F11"), win,
                    activated=lambda: win.showNormal() if win.isFullScreen() else win.showFullScreen())
    QtGui.QShortcut(QtGui.QKeySequence("Esc"), win, activated=win.showNormal)
    plots.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
    plots.setFocus()

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
            force_bar.setOpts(height=[sim["force"]], brush=RED if sim.get("broken") else GREEN)
            peak_bar.setOpts(height=[sim["peak_force"]])
            force_p.setYRange(0, max(a.break_force * 2, sim["peak_force"] * 1.1))
            force_p.setTitle("%s · %.1f N / %.1f N peak · %s" % (
                force_title, sim["force"], sim["peak_force"], "BROKEN" if sim.get("broken") else "intact"), size="16pt")
        else:
            force_bar.setOpts(height=[0]); peak_bar.setOpts(height=[0])
            force_p.setTitle(force_title, size="16pt")
        if sim and "profile" in sim and "cap" in sim:
            profile.setText("Simulation · Force Cushion: %s · Closure cap: %.0f%%" %
                            (sim["profile"], sim["cap"] * 100), color=GREEN)
        else:
            profile.setText("Simulation · Waiting for Force Cushion telemetry")
        status.setText("HANDOFF: %s" % ("HUMAN in control" if (st["button"] or st["manual"]) else "robot / auto (H = take over)"))

    t = QtCore.QTimer(); t.timeout.connect(tick); t.start(16)
    if "--selftest" in sys.argv: QtCore.QTimer.singleShot(1500, app.quit)
    if a.present: win.showFullScreen()
    else: win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
