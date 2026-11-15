"""Cut the final jury video from the demo_cv.py renders (per-frame state logs decide the cuts).
  py -3.11 g1/sim/demo_cv.py --no-show --only stress_ball --no-assist --caps stress_ball=0.7 --no-compare --out data/video/seg_ball_old.mp4 --meta data/video/seg_ball_old.json
  py -3.11 g1/sim/demo_cv.py --no-show --only can_empty,egg --out data/video/seg_assist.mp4 --meta data/video/seg_assist.json
  py -3.11 g1/sim/demo_montage.py            -> media/g1_cv_demo.mp4
Ball: pure physics take, cut just before it starts to slip (object height drops 1 cm below its peak).
Can: scan + approach + grasp, cut 0.7 s after the first lift reaches its peak (nothing after: no second grasp).
Egg: scan + grasp, cut as soon as it is lifted (peak) and that frame is held for 2 s.
Egg without vision: until it breaks, plus 1.5 s."""
import json, os, sys
import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
V = os.path.join(ROOT, "data", "video"); RATE = 30


def frames(path):
    c = cv2.VideoCapture(path); out = []
    while True:
        ok, f = c.read()
        if not ok: return out
        out.append(f)


def peak_end(meta, idx, drop=1.0):
    """last frame index (in idx) before the object height falls `drop` cm below its running peak while lifted"""
    best, best_i = -1e9, idx[0]
    for i in idx:
        m = meta[i]
        if m.get("kind") != "grasp": continue
        if m["lift"] > best: best, best_i = m["lift"], i
        elif best > 3.0 and m["lift"] < best - drop: return best_i
    return best_i


def main():
    OUT = os.path.join(ROOT, "media", sys.argv[1] if len(sys.argv) > 1 else "g1_cv_demo.mp4")
    out = cv2.VideoWriter(OUT, cv2.VideoWriter_fourcc(*"mp4v"), RATE, (1920, 1080)); n = 0
    def write(fs):
        nonlocal n
        for f in fs: out.write(f); n += 1

    # 1) ball (pure physics render): scan + grasp until just before it slips
    mb = json.load(open(os.path.join(V, "seg_ball_old.json"))); fb = frames(os.path.join(V, "seg_ball_old.mp4"))
    idx = [i for i, m in enumerate(mb) if m["seg"] == "stress_ball"]
    end = peak_end(mb, [i for i in idx if mb[i].get("kind") == "grasp" and mb[i]["state"] in ("LIFT", "GRASP")] or idx, drop=0.5)
    write(fb[idx[0]:end + 1]); print("ball  frames", idx[0], end, "s", round((end - idx[0]) / RATE, 1))

    ma = json.load(open(os.path.join(V, "seg_assist.json"))); fa = frames(os.path.join(V, "seg_assist.mp4"))
    # 2) can: until 0.7 s after the FIRST lift peak
    idx = [i for i, m in enumerate(ma) if m["seg"] == "can_empty"]
    lift_i = [i for i in idx if ma[i].get("kind") == "grasp" and ma[i]["state"] == "LIFT"]
    first = []
    for i in lift_i:                                    # first contiguous LIFT block only
        if first and i != first[-1] + 1: break
        first.append(i)
    end = min(peak_end(ma, first) + int(0.7 * RATE), first[-1])
    write(fa[idx[0]:end + 1]); print("can   frames", idx[0], end, "s", round((end - idx[0]) / RATE, 1))
    # 3) egg: until the lift peak, then hold that frame 2 s
    idx = [i for i, m in enumerate(ma) if m["seg"] == "egg"]
    lift_i = [i for i in idx if ma[i].get("kind") == "grasp" and ma[i]["state"] == "LIFT"]
    first = []
    for i in lift_i:
        if first and i != first[-1] + 1: break
        first.append(i)
    end = peak_end(ma, first)
    write(fa[idx[0]:end + 1]); write([fa[end]] * (2 * RATE)); print("egg   frames", idx[0], end, "+2 s hold")
    # 4) egg without vision: until it breaks + 1.5 s
    idx = [i for i, m in enumerate(ma) if m["seg"] == "compare"]
    brk = next((i for i in idx if ma[i].get("broken")), idx[-1])
    end = min(brk + int(1.5 * RATE), idx[-1])
    write(fa[idx[0]:end + 1]); print("noCV  frames", idx[0], end, "broken at", brk)
    out.release(); print("total s", round(n / RATE, 1), "->", OUT)


if __name__ == "__main__":
    main()
