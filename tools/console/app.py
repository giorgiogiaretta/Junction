"""Console operatore G1 (PyQt6): check pre-volo, guanti + Coil, robot MuJoCo, avvio/STOP policy.
  py -3.11 tools/console/app.py                      # guanti dal driver Rokoko 127.0.0.1:12276
  py -3.11 tools/console/app.py --gloves replay:85   # guanti da una take registrata (test senza guanti)
  py -3.11 tools/console/app.py --screenshot tools/console/screenshot.png --quit-after 12
See tools/console/README.md."""
import argparse, collections, glob, json, math, os, shlex, socket, struct, subprocess, sys, threading, time

import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [ROOT, os.path.join(ROOT, "g1"), os.path.join(ROOT, "g1", "sim"), os.path.join(ROOT, "Rokoko", "src")]
LIVE = os.path.join(ROOT, "data", "live")
TAP = os.path.join(LIVE, "head_latest.jpg")
CALIB = os.path.join(ROOT, "data", "calib.json")
ARM_CALIB = os.path.join(ROOT, "data", "arm_calib.json")
POLICIES = {"Braccia + guanti (G1 reale, veloce)": os.path.join(ROOT, "g1", "arms_glove.py"),
            "Camera + oggetto (G1 reale, visione)": os.path.join(ROOT, "g1", "arms_vision.py"),
            "V1 (senza Coil)": os.path.join(ROOT, "g1", "live_policy_v1.py"), "V2 (Coil)": os.path.join(ROOT, "g1", "live_policy_v2.py")}
OBJECTS = ["stress_ball", "can_empty", "egg"]          # first = default (pallina)
FINGERS = ["pollice", "indice", "medio", "anulare", "mignolo"]
DRIVER = ("127.0.0.1", 12276)
FWD_PORT = 14043
GREEN, YELLOW, RED, GREY = "#2e9e44", "#d9a400", "#d0302a", "#777777"


def tcp_ok(host, port, timeout=1.0):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout): return True
    except (OSError, TypeError, ValueError, OverflowError): return False


def quat_to_mat(q):  # wxyz
    w, x, y, z = q; n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0; w, x, y, z = w / n, x / n, y / n, z / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def rpy_deg(R):
    return (math.degrees(math.atan2(R[2, 1], R[2, 2])), math.degrees(math.asin(max(-1, min(1, -R[2, 0])))), math.degrees(math.atan2(R[1, 0], R[0, 0])))


# ----------------------------------------------------------------------------------------------------------- glove input
class HandState:
    def __init__(self):
        self.f01 = None; self.pos = None; self.quat = None; self.qref = ""; self.t = 0.0
        self.times = collections.deque(maxlen=400); self.flags = collections.deque(maxlen=90)
        self.trail = collections.deque(maxlen=60)


class GloveSource:
    """Background reader. live: RGMP from the Rokoko driver (data/calib.json -> fingers 0..1), optionally forwarded as
    UDP {"left","right","t"} to 127.0.0.1:14043 (the V1 policy's --source udp:14043). replay:<take>: data/episodes/take_XX.npz."""
    def __init__(self, spec="live"):
        self.spec = spec; self.lock = threading.Lock(); self.hands = {"left": HandState(), "right": HandState()}
        self.connected = False; self.error = ""; self.forward = False; self.stop = False
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        threading.Thread(target=self._run_replay if spec.startswith("replay:") else self._run_live, daemon=True).start()

    def snapshot(self):
        now = time.time(); out = {}
        with self.lock:
            for h, s in self.hands.items():
                fl = np.array(s.flags, int) if s.flags else np.zeros(0, int)
                out[h] = dict(f01=None if s.f01 is None else np.array(s.f01), pos=None if s.pos is None else np.array(s.pos),
                              quat=None if s.quat is None else np.array(s.quat), qref=s.qref, age=now - s.t if s.t else None,
                              hz=sum(1 for t in s.times if now - t <= 1.0),
                              coil=float(((fl >> 9) & 1).mean()) if fl.size else None, sat=float(((fl >> 8) & 1).mean()) if fl.size else None,
                              flip=float(((fl >> 10) & 1).mean()) if fl.size else None, trail=[np.array(p) for p in s.trail])
            return out, self.connected, self.error

    def _update(self, h, f01, pos, quat, qref, flags):
        now = time.time()
        with self.lock:
            s = self.hands[h]; s.f01 = f01; s.t = now; s.times.append(now); s.flags.append(int(flags)); s.qref = qref
            s.pos = pos; s.quat = quat
            if pos is not None and (not s.trail or now - getattr(s, "t_trail", 0) > 0.1): s.trail.append(pos); s.t_trail = now
            send = self.forward
            pkt = {k: (None if self.hands[k].f01 is None or now - self.hands[k].t > 0.5 else [round(float(x), 3) for x in self.hands[k].f01]) for k in ("left", "right")}
        if send:
            pkt["t"] = now
            try: self.udp.sendto(json.dumps(pkt).encode(), ("127.0.0.1", FWD_PORT))
            except OSError: pass

    def _run_replay(self):
        take = int(self.spec.split(":")[1]); z = np.load(os.path.join(ROOT, "data", "episodes", f"take_{take:02d}.npz"), allow_pickle=True)
        def arr(h, k):
            for src in (h, "right"):
                if f"{src}_{k}" in z.files: return z[f"{src}_{k}"]
        data = {h: (arr(h, "fingers01"), arr(h, "wrist_pos"), arr(h, "wrist_quat")) for h in ("left", "right")}
        self.connected = True; self.error = f"replay take {take}"; t0 = time.time()
        while not self.stop:
            for k, h in enumerate(("right", "left")):
                F, P, Q = data[h]; n = len(F); i = (int((time.time() - t0) * 30) + k * n // 2) % n   # left = right shifted if missing
                p = None if P is None or not np.all(np.isfinite(P[i])) else P[i].astype(float)
                q = None if Q is None or not np.all(np.isfinite(Q[i])) else Q[i].astype(float)
                self._update(h, F[i].astype(float), p, q, "coil_pro (replay)", (1 << 9) if p is not None else 0)
            time.sleep(1 / 30)

    def _run_live(self):
        import analyze_takes as A, calib
        R = A.R
        while not self.stop:
            try:
                s = socket.create_connection(DRIVER, timeout=2); s.settimeout(1.0)
                cal = calib.load(CALIB); buf, lay, names, used = b"", {}, {}, {}
                self.connected = True; self.error = ""
                while not self.stop:
                    try:
                        c = s.recv(65536)
                        if not c: raise ConnectionError("il driver ha chiuso lo stream")
                        buf += c
                    except socket.timeout: continue
                    while len(buf) >= 8:
                        typ, ln = struct.unpack_from("<II", buf, 0)
                        if len(buf) < 8 + ln: break
                        p, buf = buf[8:8 + ln], buf[8 + ln:]
                        if typ == 1:
                            sd = json.loads(p.decode("utf-8")); d = sd["device_id"]; lay[d] = R.build_layout(sd); names[d] = A.name_device(sd, used)
                        elif typ == 2:
                            d = struct.unpack_from("<I", p, 0)[0]
                            if d not in lay or names[d] not in self.hands: continue
                            _, name, ts, items = R.decode(lay[d], p)
                            if name != "default": continue
                            ang, pos, q, qref, flags = [0.0] * 5, None, None, "", 0
                            for st, v in items:
                                tf, mt, ref = st["target_frame"], st["measure_type"], st.get("reference_frame")
                                if mt == "TRANSFORM" and tf.endswith("finger_sensor"): ang[A.FRAMES.index(tf.split("_")[0])] = R.angle_of(R.quat(v))
                                elif mt == "TRANSFORM" and tf == "arm_sensor" and len(v) >= 4:
                                    qq = [v[6], v[3], v[4], v[5]] if len(v) >= 7 else [v[3], v[0], v[1], v[2]]
                                    if ref == "coil_pro":
                                        q, qref = qq, "coil_pro"
                                        if len(v) >= 7: pos = list(v[:3])
                                    elif q is None: q, qref = qq, str(ref)
                                elif mt == "STATUS_FLAGS" and tf == "arm_sensor": flags = int(v[0])
                            h = names[d]
                            f01 = calib.to01(np.array([ang]), cal[h])[0] if h in cal else np.clip(np.array(ang) / 2.5, 0, 1)
                            self._update(h, np.asarray(f01, float), pos, q, qref, flags)
            except Exception as e:  # noqa: BLE001 - reconnect forever, show the reason
                self.connected = False; self.error = str(e) or type(e).__name__
                time.sleep(1.0)


# ----------------------------------------------------------------------------------------------------------- widgets
def badge(level):
    return {"ok": GREEN, "warn": YELLOW, "fail": RED}.get(level, GREY)


class HandView(QtWidgets.QWidget):
    """2D hand skeleton (back of the hand, palm away), per-finger bend bars and a wrist orientation triad."""
    def __init__(self, side):
        super().__init__(); self.side = side; self.st = {}; self.setMinimumSize(260, 260)

    def set_state(self, st): self.st = st; self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self); p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height(); p.fillRect(0, 0, W, H, QtGui.QColor("#16181d"))
        st = self.st; f = st.get("f01"); live = f is not None and st.get("age") is not None and st["age"] < 0.5
        title = ("SINISTRA" if self.side == "left" else "DESTRA") + (f"  {st.get('hz', 0)} Hz" if st else "")
        p.setPen(QtGui.QColor("white")); p.setFont(QtGui.QFont("Segoe UI", 13, QtGui.QFont.Weight.Bold)); p.drawText(10, 22, title)
        if not live:
            p.setPen(QtGui.QColor(RED)); p.setFont(QtGui.QFont("Segoe UI", 10)); p.drawText(10, H - 10, "nessun dato dal guanto")
            f = np.zeros(5)
        sgn = -1 if self.side == "left" else 1                    # back of the hand: right thumb on the left of the drawing
        s = min(W * 0.15, (H - 60) / 4.9); cx, cy = W * 0.34, 34 + 3.6 * s
        col = QtGui.QColor("#e8e8e8" if live else "#555")
        p.setPen(QtGui.QPen(col, 3)); p.setBrush(QtGui.QColor(60, 66, 80))
        palm = QtGui.QPolygonF([QtCore.QPointF(cx + sgn * x * s, cy + y * s) for x, y in ((-1.1, -1.4), (1.1, -1.4), (1.0, 0.9), (-0.9, 0.9))])
        p.drawPolygon(palm)
        bases = [(-1.2, -0.1, 235)] + [(-0.8 + 0.53 * i, -1.4, 270) for i in range(4)]   # right hand seen from the back, y down
        lens = [(0.7, 0.55, 0.45)] + [(0.95, 0.6, 0.45)] * 4
        curls = [(30, 40, 35)] + [(70, 85, 60)] * 4                                         # deg per joint at full closure
        for i in range(5):
            x, y, a = bases[i]; bend = float(np.clip(f[i], 0, 1))
            pts = [QtCore.QPointF(cx + sgn * x * s, cy + y * s)]
            cum = 0.0
            for L, c in zip(lens[i], curls[i]):
                if i == 0: a += c * bend; x += math.cos(math.radians(a)) * L; y += math.sin(math.radians(a)) * L   # thumb: in-plane opposition
                else: cum += c * bend; y -= math.cos(math.radians(cum)) * L; x += 0.12 * math.sin(math.radians(cum)) * L   # fingers: flexion seen from the back = foreshortening / fold over the palm
                pts.append(QtCore.QPointF(cx + sgn * x * s, cy + y * s))
            c = QtGui.QColor.fromHsvF(max(0.0, 0.33 * (1 - bend)), 0.8, 0.95) if live else col
            p.setPen(QtGui.QPen(c, 7, cap=Qt.PenCapStyle.RoundCap)); p.drawPolyline(QtGui.QPolygonF(pts))
            p.setBrush(c); p.setPen(Qt.PenStyle.NoPen)
            for q in pts: p.drawEllipse(q, 4, 4)
        # bend bars
        bx0, by0 = W * 0.70, 32
        p.setFont(QtGui.QFont("Segoe UI", 9))
        for i in range(5):
            y = by0 + i * 21; v = float(np.clip(f[i], 0, 1)); p.setPen(QtGui.QColor("#ccc")); p.drawText(int(bx0), y + 12, FINGERS[i][:4])
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QtGui.QColor("#333")); p.drawRect(int(bx0 + 34), y, int(W * 0.24 - 30), 14)
            p.setBrush(QtGui.QColor.fromHsvF(max(0.0, 0.33 * (1 - v)), 0.8, 0.9)); p.drawRect(int(bx0 + 34), y, int((W * 0.24 - 30) * v), 14)
            p.setPen(QtGui.QColor("white")); p.drawText(int(bx0 + 38), y + 12, f"{v:.2f}")
        # wrist orientation triad (top view of the sensor axes)
        tr = min(W * 0.1, (H - 190) / 2.2); q = st.get("quat"); tx, ty = W * 0.84, by0 + 5 * 21 + 22 + tr
        p.setPen(QtGui.QColor("#ccc")); p.drawText(int(bx0), int(ty - tr - 4), "polso (x r, y v, z b)")
        if q is not None and live:
            Rm = quat_to_mat(q)
            for k, c in enumerate(("#ff5555", "#55dd55", "#5599ff")):
                v = Rm[:, k]; p.setPen(QtGui.QPen(QtGui.QColor(c), 3)); p.drawLine(QtCore.QPointF(tx, ty), QtCore.QPointF(tx + v[1] * -tr, ty - v[0] * tr))
            r, pi, yw = rpy_deg(Rm); p.setPen(QtGui.QColor("#ccc"))
            p.drawText(int(tx - tr), int(ty + tr + 16), f"R{r:+.0f} P{pi:+.0f} Y{yw:+.0f}°")
            p.drawText(int(tx - tr), int(ty + tr + 30), f"rif. {st.get('qref', '')}"[:22])
        else:
            p.setPen(QtGui.QColor(GREY)); p.drawText(int(tx - tr), int(ty), "orientamento --")
        p.end()


class CoilView(QtWidgets.QWidget):
    """Top (x,y) and side (x,z) view of both wrists in the Coil frame (Coil at the origin), with distance/saturation warnings."""
    RANGE = 1.0

    def __init__(self):
        super().__init__(); self.snap = {}; self.setMinimumSize(380, 240)

    def set_state(self, snap): self.snap = snap; self.update()

    def paintEvent(self, _):
        p = QtGui.QPainter(self); p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height(); p.fillRect(0, 0, W, H, QtGui.QColor("#101216"))
        pw = W / 2
        for k, (name, ax) in enumerate((("DALL'ALTO (x,y)", (0, 1)), ("DI LATO (x,z)", (0, 2)))):
            x0 = k * pw; cx, cy, sc = x0 + pw / 2, H * 0.5 + 6, min(pw, H - 70) / (2 * self.RANGE)
            p.setPen(QtGui.QColor("#ddd")); p.setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Weight.Bold)); p.drawText(int(x0 + 8), 18, name)
            p.setPen(QtGui.QPen(QtGui.QColor("#333"), 1)); p.setBrush(Qt.BrushStyle.NoBrush)
            for r in (0.25, 0.5, 0.75, 1.0): p.drawEllipse(QtCore.QPointF(cx, cy), r * sc, r * sc)
            p.drawLine(int(cx - sc), int(cy), int(cx + sc), int(cy)); p.drawLine(int(cx), int(cy - sc), int(cx), int(cy + sc))
            p.setPen(QtGui.QColor("#777")); p.setFont(QtGui.QFont("Segoe UI", 8)); p.drawText(int(cx + 0.5 * sc + 2), int(cy - 2), "0.5 m")
            p.setBrush(QtGui.QColor("#ffcc33")); p.setPen(Qt.PenStyle.NoPen); p.drawRect(int(cx - 6), int(cy - 6), 12, 12)
            p.setPen(QtGui.QColor("#ffcc33")); p.drawText(int(cx + 8), int(cy + 14), "Coil")
            for h, c in (("left", "#4fa3ff"), ("right", "#ff7a4f")):
                st = self.snap.get(h) or {}
                tr = st.get("trail") or []
                p.setPen(QtGui.QPen(QtGui.QColor(c), 1))
                for a, b in zip(tr, tr[1:]):
                    p.drawLine(QtCore.QPointF(cx + a[ax[0]] * sc, cy - a[ax[1]] * sc), QtCore.QPointF(cx + b[ax[0]] * sc, cy - b[ax[1]] * sc))
                pos = st.get("pos")
                if pos is not None and st.get("age", 9) < 0.5:
                    x, y = cx + float(np.clip(pos[ax[0]], -1.2, 1.2)) * sc, cy - float(np.clip(pos[ax[1]], -1.2, 1.2)) * sc
                    p.setBrush(QtGui.QColor(c)); p.setPen(QtGui.QPen(QtGui.QColor("white"), 1)); p.drawEllipse(QtCore.QPointF(x, y), 8, 8)
                    p.setPen(QtGui.QColor("white")); p.drawText(int(x + 10), int(y + 4), "S" if h == "left" else "D")
        # status line per hand
        p.setFont(QtGui.QFont("Segoe UI", 10, QtGui.QFont.Weight.Bold))
        for i, h in enumerate(("left", "right")):
            st = self.snap.get(h) or {}; pos = st.get("pos"); txt, col = self.status(st)
            lbl = ("SIN " if h == "left" else "DES ") + (f"dist {np.linalg.norm(pos):.2f} m  " if pos is not None else "dist --  ") + txt
            p.setPen(QtGui.QColor(col)); p.drawText(int(8 + i * pw), int(H - 10), lbl)
        p.end()

    @staticmethod
    def status(st):
        if not st or st.get("age") is None or st["age"] > 0.5: return "guanto assente", RED
        if st.get("coil") is not None and st["coil"] < 0.9: return "COIL NON VISTO", RED
        if st.get("sat") and st["sat"] > 0.05: return "SATURO: troppo vicino!", RED
        pos = st.get("pos")
        if pos is None: return "posizione assente", YELLOW
        d = float(np.linalg.norm(pos))
        if d < 0.15: return "troppo vicino al Coil", YELLOW
        if d > 1.0: return "lontano dal Coil", YELLOW
        return "OK", GREEN


class RobotView(QtWidgets.QLabel):
    """Offscreen MuJoCo render of the G1 (g1/arm_ik.G1Arms): arm_q/hand_q from the policy log or hand_q from the gloves."""
    def __init__(self):
        super().__init__("caricamento modello G1..."); self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(420, 320); self.setStyleSheet("background:#0d0f12;color:#aaa;font-size:14px")
        self.arms = self.renderer = None; self.err = ""
        try:
            import mujoco, arm_ik
            from robot.g1_dex3 import G1Dex3Retargeter
            self.mj, self.arm_ik = mujoco, arm_ik
            self.arms = arm_ik.G1Arms(with_cam=False); self.renderer = mujoco.Renderer(self.arms.m, 420, 560)
            self.cam = mujoco.MjvCamera(); self.cam.lookat[:] = [0.2, 0.0, 1.0]; self.cam.distance = 1.35; self.cam.azimuth = 150; self.cam.elevation = -22
            self.home_q = dict(self.arms.q); self.Rt = G1Dex3Retargeter
        except Exception as e:  # noqa: BLE001
            self.arms = self.renderer = None; self.err = f"MuJoCo non disponibile: {e}"; self.setText(self.err)

    def draw(self, arm_q=None, hand_q=None):
        if self.arms is None: return
        self.arms.q.update(self.home_q)
        if arm_q is not None and len(arm_q) == len(self.arm_ik.ARM_NAMES):
            self.arms.q.update({n: float(v) for n, v in zip(self.arm_ik.ARM_NAMES, arm_q)})
        self.arms.apply(hand_q if hand_q is not None and len(hand_q) == len(self.arms.hand_names) else None)
        self.renderer.update_scene(self.arms.d, self.cam); img = np.ascontiguousarray(self.renderer.render())
        qi = QtGui.QImage(img.data, img.shape[1], img.shape[0], img.shape[1] * 3, QtGui.QImage.Format.Format_RGB888).copy()
        self.setPixmap(QtGui.QPixmap.fromImage(qi).scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


class Bridge(QtCore.QObject):
    check_done = QtCore.pyqtSignal(str, str, str)   # key, level, text


# ----------------------------------------------------------------------------------------------------------- main window
class Console(QtWidgets.QMainWindow):
    CHECKS = [("driver", "Driver Rokoko (127.0.0.1:12276)"), ("gloves", "Guanti in streaming (Hz)"), ("coil", "Coil: presente / saturazione / flip"),
              ("calib", "Calibrazione dita (data/calib.json)"), ("armcal", "Calibrazione braccia (data/arm_calib.json)"),
              ("port", "Porta 8000 (policy server)"), ("runner", "PC runner raggiungibile (TCP)"), ("tap", "Frame camera testa (head_latest.jpg)"),
              ("mock", "Prova generale (mock)")]

    def __init__(self, gloves="live"):
        super().__init__(); self.setWindowTitle("Console operatore G1 - Junction 2026"); self.resize(1680, 1000)
        self.src = GloveSource(gloves); self.bridge = Bridge(); self.bridge.check_done.connect(self.set_check)
        self.policy = None; self.aux = {}; self.log_path = None; self.log_off = 0; self.last_rec = {}; self.tap_mtime = 0
        self.mock_state = None
        self._build()
        self.t_ui = QtCore.QTimer(self); self.t_ui.timeout.connect(self.tick_ui); self.t_ui.start(33)
        self.t_robot = QtCore.QTimer(self); self.t_robot.timeout.connect(self.tick_robot); self.t_robot.start(66)
        self.t_slow = QtCore.QTimer(self); self.t_slow.timeout.connect(self.tick_slow); self.t_slow.start(250)

    # ---- layout
    def _build(self):
        self.setStyleSheet("""
            QWidget{background:#1c1f26;color:#e6e6e6;font-family:'Segoe UI';font-size:13px}
            QPushButton{background:#2f3542;border:1px solid #444;border-radius:6px;padding:8px 12px;font-size:14px;font-weight:bold}
            QPushButton:hover{background:#3b4252} QPushButton:disabled{color:#666}
            QLineEdit,QComboBox,QPlainTextEdit{background:#12141a;border:1px solid #3a3f4b;border-radius:4px;padding:4px}
            QGroupBox{border:1px solid #3a3f4b;border-radius:6px;margin-top:14px;font-weight:bold;font-size:14px}
            QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 4px}""")
        central = QtWidgets.QWidget(); self.setCentralWidget(central); root = QtWidgets.QHBoxLayout(central)
        root.addWidget(self._controls(), 0)
        right = QtWidgets.QVBoxLayout(); root.addLayout(right, 1)
        top = QtWidgets.QHBoxLayout(); right.addLayout(top, 3)
        g = QtWidgets.QGroupBox("GUANTI"); gl = QtWidgets.QVBoxLayout(g)
        hands = QtWidgets.QHBoxLayout(); self.hv = {"left": HandView("left"), "right": HandView("right")}
        hands.addWidget(self.hv["left"]); hands.addWidget(self.hv["right"]); gl.addLayout(hands, 3)
        self.coil = CoilView(); gl.addWidget(self.coil, 2)
        self.glove_lbl = QtWidgets.QLabel(); gl.addWidget(self.glove_lbl)
        top.addWidget(g, 3)
        r = QtWidgets.QGroupBox("ROBOT"); rl = QtWidgets.QVBoxLayout(r)
        row = QtWidgets.QHBoxLayout(); row.addWidget(QtWidgets.QLabel("Sorgente:"))
        self.robot_src = QtWidgets.QComboBox(); self.robot_src.addItems(["log policy (data/live/*.jsonl)", "guanti dal vivo (solo mani)"]); row.addWidget(self.robot_src, 1)
        rl.addLayout(row); self.robot = RobotView(); rl.addWidget(self.robot, 3)
        self.robot_lbl = QtWidgets.QLabel("--"); self.robot_lbl.setWordWrap(True); rl.addWidget(self.robot_lbl)
        self.tap = QtWidgets.QLabel("camera testa: nessun frame\n(la policy deve scrivere data/live/head_latest.jpg)")
        self.tap.setAlignment(Qt.AlignmentFlag.AlignCenter); self.tap.setMinimumHeight(150); self.tap.setStyleSheet("background:#0d0f12;color:#888")
        rl.addWidget(self.tap, 2)
        top.addWidget(r, 2)
        bottom = QtWidgets.QHBoxLayout(); right.addLayout(bottom, 2)
        bottom.addWidget(self._checks(), 1)
        lg = QtWidgets.QGroupBox("LOG"); ll = QtWidgets.QVBoxLayout(lg)
        self.state_lbl = QtWidgets.QLabel("policy: ferma"); self.state_lbl.setStyleSheet("font-size:15px;font-weight:bold"); ll.addWidget(self.state_lbl)
        self.log = QtWidgets.QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(3000)
        self.log.setFont(QtGui.QFont("Consolas", 9)); ll.addWidget(self.log)
        bottom.addWidget(lg, 1)

    def _controls(self):
        box = QtWidgets.QGroupBox("CONTROLLI"); box.setFixedWidth(380); v = QtWidgets.QVBoxLayout(box)
        self.stop_btn = QtWidgets.QPushButton("STOP"); self.stop_btn.setMinimumHeight(110)
        self.stop_btn.setStyleSheet("QPushButton{background:#c0221b;color:white;font-size:40px;font-weight:900;border:3px solid #ff6b63;border-radius:12px}"
                                    "QPushButton:hover{background:#e02a22}")
        self.stop_btn.clicked.connect(self.stop_all); v.addWidget(self.stop_btn)
        f = QtWidgets.QFormLayout(); v.addLayout(f)
        self.ver = QtWidgets.QComboBox(); self.ver.addItems(list(POLICIES)); f.addRow("Policy", self.ver)
        self.source = QtWidgets.QLineEdit(f"udp:{FWD_PORT}"); f.addRow("Sorgente guanti", self.source)
        self.robj = QtWidgets.QComboBox(); self.robj.addItems(OBJECTS); f.addRow("Oggetto DESTRA", self.robj)
        self.rxy = QtWidgets.QLineEdit("0.35,-0.15"); f.addRow("Posizione DESTRA x,y (m)", self.rxy)
        self.lobj = QtWidgets.QComboBox(); self.lobj.addItems(OBJECTS); self.lobj.setCurrentText("can_empty"); f.addRow("Oggetto SINISTRA", self.lobj)
        self.lxy = QtWidgets.QLineEdit("0.35,0.15"); f.addRow("Posizione SINISTRA x,y (m)", self.lxy)
        self.host = QtWidgets.QLineEdit("0.0.0.0"); f.addRow("Host policy (0.0.0.0 = rete)", self.host)
        self.extra = QtWidgets.QLineEdit(""); self.extra.setPlaceholderText("argomenti extra (es. per V2)"); f.addRow("Extra", self.extra)
        self.clos_lbl = QtWidgets.QLabel(); self.clos = QtWidgets.QSlider(Qt.Orientation.Horizontal); self.clos.setRange(0, 100); self.clos.setValue(10)
        self.clos.valueChanged.connect(lambda x: self.clos_lbl.setText(f"G1_MAX_CLOSURE = {x / 100:.2f}")); self.clos.valueChanged.emit(10)
        v.addWidget(self.clos_lbl); v.addWidget(self.clos)
        self.fwd = QtWidgets.QCheckBox(f"Inoltra guanti -> UDP {FWD_PORT} (per V1)"); self.fwd.setChecked(True)
        self.fwd.toggled.connect(lambda on: setattr(self.src, "forward", on)); self.src.forward = True; v.addWidget(self.fwd)
        self.start_btn = QtWidgets.QPushButton("AVVIA POLICY"); self.start_btn.setMinimumHeight(60)
        self.start_btn.setStyleSheet("QPushButton{background:#1f7a35;font-size:20px} QPushButton:hover{background:#26903f}")
        self.start_btn.clicked.connect(self.start_policy); v.addWidget(self.start_btn)
        self.cal_btn = QtWidgets.QPushButton("Calibra (Coil)"); self.cal_btn.setMinimumHeight(48); self.cal_btn.clicked.connect(self.calibrate); v.addWidget(self.cal_btn)
        f2 = QtWidgets.QFormLayout(); v.addLayout(f2)
        self.aalto = QtWidgets.QLineEdit(os.environ.get("AALTO_REPO", r"C:\Users\giorg\Desktop\aaltonomous-humanoid")); f2.addRow("AALTO_REPO", self.aalto)
        v.addStretch(1)
        self.ver.currentTextChanged.connect(self._ver_changed); self._ver_changed(self.ver.currentText())
        return box

    def _checks(self):
        box = QtWidgets.QGroupBox("CHECK PRE-VOLO"); v = QtWidgets.QVBoxLayout(box)
        row = QtWidgets.QHBoxLayout()
        b = QtWidgets.QPushButton("Esegui tutti i check"); b.setMinimumHeight(48); b.setStyleSheet("QPushButton{background:#2456a6;font-size:17px}")
        b.clicked.connect(self.run_checks); row.addWidget(b, 2)
        self.mock_btn = QtWidgets.QPushButton("Prova generale (mock)"); self.mock_btn.setMinimumHeight(48); self.mock_btn.clicked.connect(self.run_mock); row.addWidget(self.mock_btn, 1)
        v.addLayout(row)
        row2 = QtWidgets.QHBoxLayout(); row2.addWidget(QtWidgets.QLabel("IP PC runner:"))
        self.rip = QtWidgets.QLineEdit("192.168.123.164"); row2.addWidget(self.rip, 2); row2.addWidget(QtWidgets.QLabel("porta:"))
        self.rport = QtWidgets.QLineEdit("22"); self.rport.setMaximumWidth(60); row2.addWidget(self.rport); v.addLayout(row2)
        grid = QtWidgets.QGridLayout(); v.addLayout(grid); self.rows = {}
        for i, (k, name) in enumerate(self.CHECKS):
            dot = QtWidgets.QLabel(); dot.setFixedSize(22, 22); dot.setStyleSheet(f"background:{GREY};border-radius:11px")
            n = QtWidgets.QLabel(name); n.setStyleSheet("font-weight:bold")
            t = QtWidgets.QLabel("--"); t.setWordWrap(True)
            grid.addWidget(dot, i, 0); grid.addWidget(n, i, 1); grid.addWidget(t, i, 2); self.rows[k] = (dot, t)
        grid.setColumnStretch(2, 1); v.addStretch(1)
        return box

    def _ver_changed(self, name):
        ok = os.path.exists(POLICIES[name]); self.start_btn.setEnabled(ok)
        self.start_btn.setText("AVVIA POLICY " + name.split()[0] if ok else f"{os.path.basename(POLICIES[name])} non presente")

    # ---- logging
    def say(self, msg): self.log.appendPlainText(time.strftime("%H:%M:%S ") + msg)

    def set_check(self, key, level, text):
        dot, t = self.rows[key]; dot.setStyleSheet(f"background:{badge(level)};border-radius:11px"); t.setText(text)

    # ---- checks
    def run_checks(self):
        for k, _ in self.CHECKS:
            if k != "mock": self.set_check(k, "", "...")
        threading.Thread(target=self._checks_worker, args=(self.rip.text().strip(), self.rport.text().strip()), daemon=True).start()

    def _checks_worker(self, rip, rport):
        E = self.bridge.check_done.emit
        E("driver", "ok" if tcp_ok(*DRIVER) else "fail", "raggiungibile" if tcp_ok(*DRIVER) else "NON raggiungibile: avvia rokoko-sdk --auto-stream-usb")
        time.sleep(1.2)                                              # let the rate window fill
        snap, conn, err = self.src.snapshot()
        hz = {h: snap[h]["hz"] for h in snap}; lv = "ok" if min(hz.values()) >= 25 else ("warn" if max(hz.values()) > 0 else "fail")
        E("gloves", lv, f"sinistra {hz['left']} Hz, destra {hz['right']} Hz" + ("" if conn else f"  ({err})"))
        parts, lv = [], "ok"
        for h, n in (("left", "SIN"), ("right", "DES")):
            s = snap[h]
            if s["coil"] is None: parts.append(f"{n}: --"); lv = "fail"; continue
            parts.append(f"{n}: Coil {s['coil']:.0%} sat {s['sat']:.0%} flip {s['flip']:.0%}")
            if s["coil"] < 0.9 or s["sat"] > 0.05: lv = "fail"
        E("coil", lv, " | ".join(parts) + ("  (serve solo per V2)" if lv != "ok" else ""))
        try:
            c = json.load(open(CALIB)); miss = [h for h in ("left", "right") if h not in c]
            E("calib", "ok" if not miss else "warn", "sinistra + destra presenti" if not miss else f"manca: {', '.join(miss)}")
        except Exception as e:  # noqa: BLE001
            E("calib", "fail", f"assente/illeggibile: {e}")
        try:
            c = json.load(open(ARM_CALIB)); age = (time.time() - os.path.getmtime(ARM_CALIB)) / 3600; hands = list((c.get("hands") or {}).keys())
            lv = "ok" if age < 12 and hands else "warn"
            E("armcal", lv, f"età {age:.1f} h, calibrazione tavolo: {', '.join(hands) or 'NO (premi Calibra)'}; fonte: {str(c.get('source', '?'))[:50]}")
        except Exception as e:  # noqa: BLE001
            E("armcal", "fail", f"assente/illeggibile: {e}")
        listening = tcp_ok("127.0.0.1", 8000, 0.5); running = self.policy is not None
        if running: E("port", "ok" if listening else "warn", "policy in ascolto" if listening else "policy avviata ma porta non ancora in ascolto")
        else: E("port", "warn" if listening else "ok", "OCCUPATA da un altro processo" if listening else "libera (pronta per la policy)")
        if not rip: E("runner", "", "inserisci l'IP")
        else:
            ok = tcp_ok(rip, rport or 22, 1.5); E("runner", "ok" if ok else "fail", f"{rip}:{rport} {'raggiungibile' if ok else 'NON raggiungibile'}")
        if os.path.exists(TAP):
            age = time.time() - os.path.getmtime(TAP); E("tap", "ok" if age < 2 else "warn", f"ultimo frame {age:.1f} s fa")
        else: E("tap", "warn", "nessun file (la policy non scrive ancora il tap: opzionale)")

    # ---- processes
    def _proc(self, key, args, env_extra=None, on_finish=None):
        p = QtCore.QProcess(self); p.setWorkingDirectory(ROOT); p.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
        env = QtCore.QProcessEnvironment.systemEnvironment(); env.insert("PYTHONUNBUFFERED", "1"); env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("G1_MAX_CLOSURE", f"{self.clos.value() / 100:.2f}"); env.insert("AALTO_REPO", self.aalto.text().strip())
        for k, v in (env_extra or {}).items(): env.insert(k, v)
        p.setProcessEnvironment(env); buf = []
        def out():
            txt = bytes(p.readAllStandardOutput()).decode("utf-8", "replace"); buf.append(txt)
            for line in txt.splitlines():
                if line.strip(): self.log.appendPlainText(f"[{key}] {line}")
        p.readyReadStandardOutput.connect(out)
        def fin(code, _st):
            self.say(f"[{key}] terminato (codice {code})")
            if self.aux.get(key) is p: self.aux.pop(key, None)
            if key == "policy" and self.policy is p: self.policy = None; self.state_lbl.setText("policy: ferma")
            if on_finish: on_finish(code, "".join(buf))
        p.finished.connect(fin)
        self.say(f"[{key}] avvio: {' '.join(args)}  (G1_MAX_CLOSURE={self.clos.value() / 100:.2f})")
        p.start(sys.executable, args); self.aux[key] = p
        return p

    def policy_args(self, source=None, host=None, port=8000):
        script = POLICIES[self.ver.currentText()]
        a = [script, "--source", source or self.source.text().strip(), "--right", self.robj.currentText(), "--left", self.lobj.currentText(),
             "--host", host or self.host.text().strip() or "127.0.0.1", "--port", str(port)]
        if self.rxy.text().strip(): a += ["--right-xy", self.rxy.text().strip()]
        if self.lxy.text().strip(): a += ["--left-xy", self.lxy.text().strip()]
        return a + shlex.split(self.extra.text())

    def start_policy(self, source=None, host=None, port=8000):
        if self.policy is not None: self.say("policy già in esecuzione: premi STOP prima"); return False
        if tcp_ok("127.0.0.1", port, 0.3): self.say(f"porta {port} occupata da un altro processo: non avvio"); return False
        self.policy = self._proc("policy", self.policy_args(source, host, port)); self.state_lbl.setText(f"policy: AVVIATA ({self.ver.currentText()})")
        self.log_path = None; self.last_rec = {}; self.policy_start = time.time()
        return True

    @staticmethod
    def _kill(p):
        if p is None or p.state() == QtCore.QProcess.ProcessState.NotRunning: return
        if p.state() == QtCore.QProcess.ProcessState.Starting: p.waitForStarted(3000)
        pid = p.processId()
        if os.name == "nt" and pid: subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)   # whole tree
        if not p.waitForFinished(2000): p.kill(); p.waitForFinished(2000)

    def stop_all(self):
        self.say("STOP premuto: termino policy e processi della console")
        self.mock_state = None
        for k in list(self.aux): self._kill(self.aux.get(k))
        self.policy = None; self.state_lbl.setText("policy: FERMATA (STOP)")

    def calibrate(self):
        if "calib" in self.aux: self.say("calibrazione già in corso"); return
        if QtWidgets.QMessageBox.question(self, "Calibra (Coil)", "Calibrazione al tavolo, ~25 s per mano con beep.\nMano PIATTA al centro del tavolo, poi avanti 20 cm, indietro, a sinistra 20 cm.\nSegui i messaggi nel LOG. Iniziare?") != QtWidgets.QMessageBox.StandardButton.Yes: return
        self._proc("calib", [os.path.join(ROOT, "tools", "console", "calib_coil.py")])

    # ---- mock rehearsal: V1 replay policy on localhost + organisers' mock runner (g1/run_mock_gate.py)
    def run_mock(self):
        if self.mock_state: self.say("prova generale già in corso"); return
        if self.policy is not None: self.say("ferma la policy prima della prova generale"); return
        if not os.path.isdir(self.aalto.text().strip()): self.set_check("mock", "fail", "AALTO_REPO non trovato"); return
        self.log_path = None; self.mock_log_start = {f: os.path.getsize(f) for f in glob.glob(os.path.join(LIVE, "*.jsonl"))}
        self.mock_port = next((p for p in (8000, 8765, 8766, 8767) if not tcp_ok("127.0.0.1", p, 0.2)), None)   # 8000 busy -> rehearse on a spare port
        if self.mock_port is None or not self.start_policy(source="replay:77,78", host="127.0.0.1", port=self.mock_port):
            self.set_check("mock", "fail", "nessuna porta libera"); return
        self.mock_state = ("wait", time.time()); self.set_check("mock", "", f"policy (replay 77,78) in avvio su porta {self.mock_port}...")

    def _mock_tick(self):
        if not self.mock_state: return
        st, t0 = self.mock_state
        if st == "wait":
            if self.policy is None: self.mock_state = None; self.set_check("mock", "fail", "la policy si è chiusa: vedi LOG"); return
            if tcp_ok("127.0.0.1", self.mock_port, 0.2):
                self.mock_state = ("run", time.time()); self.set_check("mock", "", "runner mock in corso (20 s)...")
                self._proc("mock", [os.path.join(ROOT, "g1", "run_mock_gate.py"), "--policy", f"ws://localhost:{self.mock_port}", "--team", "giorgio", "--episodes", "1", "--time-limit", "20"],
                           on_finish=self._mock_done)
            elif time.time() - t0 > 90: self.mock_state = None; self.set_check("mock", "fail", "policy non in ascolto dopo 90 s"); self._kill(self.policy)

    def _mock_done(self, code, out):
        self.mock_state = None; hz = clipped = end = None
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0].isdigit():
                end, hz, clipped = parts[1], parts[2], parts[3]
        blocked, aborts = 0, 0
        for f in glob.glob(os.path.join(LIVE, "*.jsonl")):
            with open(f, encoding="utf-8", errors="replace") as fh:
                fh.seek(self.mock_log_start.get(f, 0))
                for line in fh:
                    try: d = json.loads(line)
                    except ValueError: continue
                    if not isinstance(d, dict): continue
                    try: blocked = max(blocked, int(d.get("blocked", 0) or 0))
                    except (TypeError, ValueError): pass
                    aborts += d.get("event") == "ABORT"
        self._kill(self.policy)
        try: ok = hz is not None and float(hz) >= 25 and int(clipped) == 0 and aborts == 0
        except ValueError: ok = False
        self.set_check("mock", "ok" if ok else "fail", f"command_hz {hz}  clipped {clipped}  blocked max {blocked}  abort {aborts}  ({end}, codice {code})")
        self.say(f"PROVA GENERALE: command_hz={hz} clipped={clipped} blocked_max={blocked} abort={aborts} fine={end}")

    # ---- timers
    def tick_ui(self):
        snap, conn, err = self.src.snapshot(); self.snap = snap
        for h in ("left", "right"): self.hv[h].set_state(snap[h])
        self.coil.set_state(snap)
        self.glove_lbl.setText(("driver: connesso" if conn else f"driver: NON connesso ({err})") + ("" if not self.src.spec.startswith("replay") else f"  [{self.src.spec}]")
                               + (f"   inoltro UDP {FWD_PORT}: {'ON' if self.src.forward else 'off'}"))

    def tick_robot(self):
        arm_q = hand_q = None
        if self.robot_src.currentIndex() == 0:
            d = self.last_rec; arm_q = d.get("arm_q_target") or d.get("arm_q_cmd") or d.get("arm_q"); hand_q = d.get("hand_q_target") or d.get("hand_q")
            if arm_q is not None and len(arm_q) and isinstance(arm_q[0], list): arm_q = arm_q[-1]
            if hand_q is not None and len(hand_q) and isinstance(hand_q[0], list): hand_q = hand_q[-1]
        elif self.robot.arms is not None:
            if not hasattr(self, "rt_live") or abs(self.rt_live.max_closure - self.clos.value() / 100) > 1e-6:
                self.rt_live = self.robot.Rt(max_closure=self.clos.value() / 100)
            s = getattr(self, "snap", {}); f = {h: (None if s.get(h, {}).get("f01") is None else list(s[h]["f01"])) for h in ("left", "right")}
            hand_q = self.rt_live.step(left=f["left"], right=f["right"])
        try: self.robot.draw(arm_q, hand_q)
        except Exception as e:  # noqa: BLE001
            self.robot_lbl.setText(f"errore render: {e}")

    def tick_slow(self):
        self._mock_tick()
        # newest policy log, tail new lines
        files = glob.glob(os.path.join(LIVE, "*.jsonl"))
        if files:
            newest = max(files, key=os.path.getmtime)
            if self.policy is not None and os.path.getmtime(newest) < getattr(self, "policy_start", 0): newest = None   # old run: wait for the new log
            if newest and newest != self.log_path: self.log_path = newest; self.log_off = max(0, os.path.getsize(newest) - 4000)
            try:
                with open(newest, "rb") as fh:          # bytes: exact offsets with CRLF logs
                    fh.seek(self.log_off); raw = fh.read(); cut = raw.rfind(b"\n") + 1; self.log_off += cut
                for line in raw[:cut].decode("utf-8", "replace").splitlines():
                    try: d = json.loads(line)
                    except ValueError: continue
                    if not isinstance(d, dict): continue
                    if "event" in d: self.say(f"[log] {line[:300]}")
                    else: self.last_rec = d
            except (OSError, TypeError): pass
        d = self.last_rec
        if d:
            self.robot_lbl.setText(f"{os.path.basename(self.log_path or '')}  t={d.get('t')}  stato={d.get('state')}  blocked={d.get('blocked')}  "
                                   f"abort={d.get('abort')}  pick={d.get('pick')}" + ("" if any(k in d for k in ("arm_q", "arm_q_target", "arm_q_cmd")) else "  (braccia: il log non ha arm_q -> posa home)"))
        if self.policy is not None and d:
            ab = d.get("abort"); self.state_lbl.setText(f"policy: IN ESECUZIONE  stato={d.get('state')}  blocked={d.get('blocked')}" + ("  ABORT!" if ab else ""))
            self.state_lbl.setStyleSheet(f"font-size:15px;font-weight:bold;color:{RED if ab else GREEN}")
        # head-camera frame tap
        if os.path.exists(TAP):
            mt = os.path.getmtime(TAP); age = time.time() - mt
            if mt != self.tap_mtime:
                pm = QtGui.QPixmap(TAP)
                if not pm.isNull(): self.tap_mtime = mt; self.tap.setPixmap(pm.scaled(self.tap.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.tap.setToolTip(f"frame di {age:.1f} s fa"); self.tap.setStyleSheet(f"background:#0d0f12;border:3px solid {GREEN if age < 2 else RED}")

    def closeEvent(self, e):
        if self.policy is not None and not getattr(self, "auto", False) and QtWidgets.QMessageBox.question(self, "Uscita", "La policy è in esecuzione: fermarla e uscire?") != QtWidgets.QMessageBox.StandardButton.Yes:
            e.ignore(); return
        self.stop_all(); self.src.stop = True; e.accept()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--gloves", default="live", help="live | replay:<take>")
    ap.add_argument("--screenshot"); ap.add_argument("--quit-after", type=float, default=0); ap.add_argument("--checks", action="store_true", help="run all checks at start")
    ap.add_argument("--mock", action="store_true", help="start the mock rehearsal at start"); a = ap.parse_args()
    app = QtWidgets.QApplication(sys.argv); w = Console(a.gloves); w.auto = bool(a.quit_after); w.show()
    if a.checks: QtCore.QTimer.singleShot(1500, w.run_checks)
    if a.mock: QtCore.QTimer.singleShot(2000, w.run_mock)
    if a.screenshot: QtCore.QTimer.singleShot(int(max(a.quit_after - 0.5, 1) * 1000), lambda: (w.grab().save(a.screenshot), print("screenshot:", a.screenshot)))
    if a.quit_after: QtCore.QTimer.singleShot(int(a.quit_after * 1000), w.close)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
