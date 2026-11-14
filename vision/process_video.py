"""video + take_NN_frames.json  ->  npz aligned to the PC wall clock.

  python -m vision.process_video data/video/take_01.mp4                      # auto calibration, writes data/vision/take_01.npz
  python -m vision.process_video clip.mp4 --manual                            # click the 4 markers (BL,TL,TR,BR)
  python -m vision.process_video clip.mp4 --calib data/vision/calib.json --hfov 120 --debug data/video_debug/take_01

npz keys (N = frames):  t_wall[N] (s, PC clock, from _frames.json), frame[N], can_xy[N,2] (m, table frame, NaN if lost),
can_q[N] (0 lost, 1 partial/held, 2 ok), can_area_cm2[N], wrist_xy[N,2,2] / index_xy[N,2,2] (frame, hand slot, xy; NaN missing),
hand_score[N,2], hand_xy_wrist[N,2] / hand_xy_index[N,2] (hand nearest to the can, NaN if none), hand_ok[N] (bool),
cam_ok[N] (bool, camera-motion tracking succeeded; all True for a fixed camera), calib_json, meta_json.
Table frame: origin at the centre of the marker square, x = BL->BR, y = BL->TL, metres."""
import argparse, json, os, sys
import cv2
import numpy as np

if __package__ in (None, ""):                       # allow `python vision/process_video.py`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "vision"
from vision.markers import detect_markers, calibrate_from_frames, pick_manual
from vision.homography import TableCalib, intrinsics_from_hfov, CameraMotion, jitter_mm, table_corners
from vision.can_track import CanTracker, build_background, Q_OK, Q_PARTIAL, Q_LOST
from vision.hand_track import HandTracker, nearest_to

def read_frame(cap, i):
    cap.set(cv2.CAP_PROP_POS_FRAMES, i); ok, f = cap.read(); return f if ok else None

def draw_overlay(img, calib, can, hands_px, M=None):
    v = img.copy()
    inv = np.linalg.inv(M) if M is not None else np.eye(3)
    def P(p): return cv2.perspectiveTransform(np.asarray(p, float).reshape(-1, 1, 2), inv).reshape(-1, 2)
    sq = P(calib.table_to_pixel(table_corners(calib.side))).astype(np.int32)
    cv2.polylines(v, [sq], True, (0, 255, 0), 2)
    for name, q in zip(["BL", "TL", "TR", "BR"], sq): cv2.putText(v, name, tuple(int(x) for x in q), 0, 0.6, (0, 255, 0), 2)
    if can["px"] is not None:
        u = P(can["px"])[0]; cv2.circle(v, (int(u[0]), int(u[1])), 12, (0, 0, 255), 3)
    if can["q"] and not np.isnan(can["xy"][0]):
        cv2.putText(v, "can %.3f %.3f q%d" % (*can["xy"], can["q"]), (10, 30), 0, 0.8, (0, 0, 255), 2)
    for h in hands_px:
        for k, col in (("wrist", (255, 0, 0)), ("index", (0, 255, 255))):
            cv2.circle(v, (int(h[k][0]), int(h[k][1])), 8, col, -1)
    return v

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video"); ap.add_argument("--frames", help="_frames.json (default: next to the video)")
    ap.add_argument("--out"); ap.add_argument("--calib", help="saved calibration json (skips marker detection)")
    ap.add_argument("--save-calib", help="write the calibration used to this json")
    ap.add_argument("--manual", action="store_true", help="click the 4 markers on the first frame")
    ap.add_argument("--points", help="json with 4 pixel points BL,TL,TR,BR")
    ap.add_argument("--ref-frame", type=int, help="calibrate from this single frame instead of the multi-frame vote")
    ap.add_argument("--rotate", type=int, default=0); ap.add_argument("--hfov", type=float, help="horizontal FOV in degrees (enables height correction)")
    ap.add_argument("--intrinsics", help="json with K (3x3) and dist")
    ap.add_argument("--stabilize", action="store_true", help="hand-held / moving camera: track camera motion vs the reference frame")
    ap.add_argument("--can-hsv", help="optional can colour range 'h0,s0,v0,h1,s1,v1' (OpenCV HSV), AND-ed with the foreground")
    ap.add_argument("--no-hands", action="store_true"); ap.add_argument("--step", type=int, default=1, help="process every Nth frame")
    ap.add_argument("--debug", help="write overlay frames (every 15th) to this folder (keep out of git)")
    ap.add_argument("--max-frames", type=int); ap.add_argument("--start", type=int, default=0, help="first frame to process")
    a = ap.parse_args(argv)

    cap = cv2.VideoCapture(a.video)
    if not cap.isOpened(): sys.exit("cannot open " + a.video)
    nf = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    W, H = int(cap.get(3)), int(cap.get(4))
    fj = a.frames or os.path.splitext(a.video)[0] + "_frames.json"
    synthetic_time = not os.path.exists(fj)
    if synthetic_time:
        print(f"WARNING: {fj} not found: using t = i/fps (NOT aligned to the wall clock)", file=sys.stderr)
        tw = np.arange(nf) / fps
    else:
        tw = np.array(json.load(open(fj)), float)
        if len(tw) != nf: print(f"WARNING: {len(tw)} timestamps vs {nf} video frames", file=sys.stderr)
    last = min(nf, len(tw)) if not synthetic_time else nf
    if a.max_frames: last = min(last, a.max_frames)

    K = dist = None
    if a.intrinsics:
        d = json.load(open(a.intrinsics)); K, dist = d["K"], d.get("dist")
    elif a.hfov: K = intrinsics_from_hfov(W, H, a.hfov)

    # ---- calibration
    sidx = [int(i) for i in np.linspace(a.start, last - 1, 40)]
    sample = [read_frame(cap, i) for i in sidx]
    sample = [f for f in sample if f is not None]
    ref_idx, calib, motion = a.start, None, None
    if a.stabilize: motion = CameraMotion(sample[0])
    def stab(f):
        if motion is None: return f, None, True
        M, ok = motion.to_ref(f); return cv2.warpPerspective(f, M, (W, H)), M, ok
    if a.calib:
        calib = TableCalib.load(a.calib)
        if K is not None: calib.K = np.asarray(K); calib.set_points(calib.img_pts)
    else:
        if a.points: pts = np.array(json.load(open(a.points)), float)
        elif a.manual: pts = pick_manual(sample[0])
        elif a.ref_frame is not None: ref_idx = a.ref_frame; pts = detect_markers(read_frame(cap, ref_idx), a.rotate)[0]
        else:
            tr = [stab(f)[1] for f in sample] if motion else None
            pts, info = calibrate_from_frames(sample, a.rotate, transforms=tr)
            print("marker vote:", info)
        if pts is None: sys.exit("markers not found automatically: rerun with --manual (click BL,TL,TR,BR) or --points file.json")
        calib = TableCalib(pts, K=K, dist=dist)
    if a.save_calib: calib.save(a.save_calib)
    print("calibration: marker px", calib.img_pts.round(1).tolist(), "| side", calib.side, "m | height model:", calib.R is not None)

    # ---- background model (fixed camera: temporal median)
    bgf = [stab(f)[0] for f in sample]
    can_hsv = None
    if a.can_hsv: v = [int(x) for x in a.can_hsv.split(",")]; can_hsv = (v[:3], v[3:])
    can = CanTracker(calib, build_background(bgf), can_hsv)
    hands = None if a.no_hands else HandTracker()
    if a.debug: os.makedirs(a.debug, exist_ok=True)

    idx = list(range(a.start, last, a.step)); n = len(idx)
    R = dict(can_xy=np.full((n, 2), np.nan), can_q=np.zeros(n, np.int8), can_area_cm2=np.zeros(n),
             wrist_xy=np.full((n, 2, 2), np.nan), index_xy=np.full((n, 2, 2), np.nan), hand_score=np.zeros((n, 2)),
             hand_xy_wrist=np.full((n, 2), np.nan), hand_xy_index=np.full((n, 2), np.nan), hand_ok=np.zeros(n, bool),
             cam_ok=np.ones(n, bool))
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0); pos = 0
    for j, i in enumerate(idx):
        if pos != i: cap.set(cv2.CAP_PROP_POS_FRAMES, i); pos = i
        ok, f = cap.read(); pos += 1
        if not ok: n = j; break
        s, M, cam_ok = stab(f)
        R["cam_ok"][j] = cam_ok
        c = can.update(s)
        R["can_xy"][j], R["can_q"][j], R["can_area_cm2"][j] = c["xy"], c["q"], c["area_cm2"]
        hp = []
        if hands is not None:
            h = hands.update(f, calib, M)
            R["wrist_xy"][j], R["index_xy"][j], R["hand_score"][j] = h["wrist"], h["index"], h["score"]
            hp = hands.pixels(f) if a.debug and j % 15 == 0 else []
            ref_xy = c["xy"] if not np.isnan(c["xy"][0]) else None
            k = nearest_to(h["wrist"], ref_xy) if ref_xy is not None else (int(np.argmax(h["score"])) if h["score"].max() > 0 else None)
            if k is not None and not np.isnan(h["wrist"][k][0]):
                R["hand_xy_wrist"][j], R["hand_xy_index"][j], R["hand_ok"][j] = h["wrist"][k], h["index"][k], True
        if a.debug and j % 15 == 0:
            cv2.imwrite(os.path.join(a.debug, f"f{i:05d}.jpg"), draw_overlay(f, calib, c, hp, M))
    R = {k: v[:n] for k, v in R.items()}
    out = a.out or os.path.join("data", "vision", os.path.splitext(os.path.basename(a.video))[0] + ".npz")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    meta = dict(video=os.path.basename(a.video), fps=fps, size=[W, H], synthetic_time=synthetic_time, stabilized=a.stabilize,
                hfov=a.hfov, side=calib.side, step=a.step)
    np.savez_compressed(out, t_wall=tw[idx][:n], frame=np.array(idx[:n]), calib_json=json.dumps(calib.to_json()),
                        meta_json=json.dumps(meta), **R)
    q = R["can_q"]
    print(f"{out}: {n} frames | can ok {np.mean(q == Q_OK):.0%} partial/held {np.mean(q == Q_PARTIAL):.0%} lost {np.mean(q == Q_LOST):.0%}"
          f" | hand {np.mean(R['hand_ok']):.0%}" + (" | cam tracking lost on %d frames" % (~R["cam_ok"]).sum() if a.stabilize else ""))
    return out

if __name__ == "__main__":
    main()
