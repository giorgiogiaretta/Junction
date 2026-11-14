"""One-shot check before the real takes: gloves + Coil + DJI camera together, and the camera delay.
  py -3.11 tools/sync_check.py [--cam 1] [--secs 20]
Records 20 s: 0-12 s HEAD STILL, right hand in front of the camera, 3-4 sharp fists 2 s apart; 12-20 s turn the head left/right/up/down.
Then reports: per glove samples/Coil/saturation, head glove motion during the head turn, camera fps/gaps, and the camera delay =
lag that best aligns video motion (frame difference) with the right-hand closing speed (index+middle). Files: data/sync_check/."""
import argparse, json, os, socket, struct, sys, threading, time
import numpy as np, cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "Rokoko", "src"))
import analyze_takes as A
from cam import CamRecorder

OUT = os.path.join(ROOT, "data", "sync_check")
HDR = struct.Struct("<dI")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cam", type=int, default=1); ap.add_argument("--secs", type=float, default=20); a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True); raw = os.path.join(OUT, "sync_check.rgmp")
    cam = CamRecorder(a.cam); print(f"camera {a.cam}: {cam.w}x{cam.h}"); time.sleep(1.0)
    sock = socket.create_connection(("127.0.0.1", 12276)); stop = threading.Event(); t0 = time.time()
    def rec():
        with open(raw, "wb") as f:
            while not stop.is_set():
                try: b = sock.recv(65536)
                except OSError: break
                if not b: break
                f.write(HDR.pack(time.time() - t0, len(b)) + b)
    th = threading.Thread(target=rec, daemon=True); th.start()
    cwd = os.getcwd(); os.chdir(ROOT); cam.start(0); os.chdir(cwd); vt0 = time.time()
    print("REC. TESTA FERMA, mano destra davanti alla camera: PUGNO DI SCATTO ogni 2 secondi (3-4 volte)")
    while time.time() - t0 < a.secs:
        el = time.time() - t0
        if 12 <= el < 12.2: print("ORA gira la TESTA: sinistra, destra, su, giu' (mano ferma)")
        time.sleep(0.2)
    os.chdir(ROOT); v = cam.stop(); os.chdir(cwd); cam.close(); stop.set(); sock.close(); th.join(timeout=2)
    for ext in (".mp4", "_frames.json"):                       # keep the check video out of the take numbering
        src = os.path.join(ROOT, "data", "video", "take_00" + ext); dst = os.path.join(OUT, "sync_check" + ext)
        if os.path.exists(src): os.replace(src, dst)
    v["video"] = os.path.relpath(os.path.join(OUT, "sync_check.mp4"), ROOT)
    print("stop. analisi...")
    rep = {}
    rows = A.parse(raw)
    vid = os.path.join(ROOT, v["video"]); vtimes = np.array(json.load(open(vid.replace(".mp4", "_frames.json"))))
    for h, r in rows.items():
        if len(r) < 20: continue
        ts = np.array([x[0] for x in r]); fl = np.array([x[3] for x in r]); P = np.array([x[2] if x[2] else [np.nan] * 3 for x in r], float)
        rep[h] = {"samples": len(r), "rate_hz": round(len(r) / (ts[-1] - ts[0] + 1e-9), 1), "coil_present": round(float(((fl >> 9) & 1).mean()), 3),
                  "saturation": round(float(((fl >> 8) & 1).mean()), 3), "pos_missing": round(float(np.isnan(P).any(1).mean()), 3),
                  "dist_from_coil_m": round(float(np.nanmedian(np.linalg.norm(P, axis=1))), 2) if not np.isnan(P).all() else None}
        late = (ts - ts[0]) > 12
        if late.any() and not np.isnan(P[late]).all(): rep[h]["pos_range_head_turn_cm"] = [round(100 * float(np.nanmax(P[late, k]) - np.nanmin(P[late, k])), 1) for k in range(3)]
    dv = np.diff(vtimes); rep["camera"] = {"frames": len(vtimes), "fps": round(1 / float(np.median(dv)), 1), "max_gap_ms": round(1000 * float(dv.max()), 0), "video": v["video"]}
    # camera delay: right-hand closing speed (glove, PC clock) vs video motion energy (frame time = PC clock at grab)
    if "right" in rows and len(rows["right"]) > 50:
        r = rows["right"]; gts = np.array([x[0] for x in r]); ang = np.array([x[1] for x in r]); gts = gts - gts[0]
        # glove device timestamps -> PC clock: align the first glove sample to the first raw chunk time (receive time, ~ms)
        chunk_t = []
        with open(raw, "rb") as f:
            while len(hh := f.read(HDR.size)) == HDR.size: tt, n = HDR.unpack(hh); f.seek(n, 1); chunk_t.append(tt)
        gpc = t0 + chunk_t[0] + gts
        flex = ang[:, 1:3].mean(1); gs = np.abs(np.gradient(flex, gpc))
        cap = cv2.VideoCapture(vid); prev, me = None, []
        while True:
            ok, f = cap.read()
            if not ok: break
            g = cv2.cvtColor(cv2.resize(f, (320, 180)), cv2.COLOR_BGR2GRAY).astype(np.float32)[110:180, 100:260]   # lower-centre band = the hand (people in the background excluded)
            me.append(0.0 if prev is None else float(np.abs(g - prev).mean())); prev = g
        me = np.array(me[:len(vtimes)]); vt = vtimes[:len(me)]
        grid = np.arange(max(gpc[0], vt[0]) + 1.0, min(gpc[-1], vt[-1], t0 + 11.5), 1 / 100)
        if len(grid) > 300:
            G = np.interp(grid, gpc, gs); G = (G - G.mean()) / (G.std() + 1e-9)
            best = max(((lag, float(np.mean(G * ((lambda V: (V - V.mean()) / (V.std() + 1e-9))(np.interp(grid + lag, vt, me)))))) for lag in np.arange(-0.2, 0.6, 0.01)), key=lambda x: x[1])
            rep["camera_delay_s"] = {"delay": round(best[0], 2), "corr": round(best[1], 2),
                                     "note": "video event appears this many seconds AFTER the glove event; corr < 0.3 = unreliable (fists not visible / head moved)"}
    rep["t0_wall"] = t0; rep["first_frame_after_t0_s"] = round(float(vtimes[0] - t0), 3)
    rep["note_dist"] = "dist_from_coil_m is the norm in the Coil frame: its origin is not the Coil body, do not read it as a physical distance"
    json.dump(rep, open(os.path.join(OUT, "report.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))
    ok = [h for h in ("right", "left") if h in rep and rep[h]["coil_present"] > 0.9 and rep[h]["saturation"] < 0.05]
    print("\nRISULTATO:", "OK guanti e Coil" if len(ok) == 2 else f"PROBLEMA guanti/Coil (ok: {ok})", "|",
          f"ritardo camera {rep.get('camera_delay_s', {}).get('delay')} s (corr {rep.get('camera_delay_s', {}).get('corr')})")


if __name__ == "__main__":
    main()
