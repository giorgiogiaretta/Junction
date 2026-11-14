"""Where on the table can the G1 see AND grasp each object? Grid of placements on the mat (pelvis frame), for each:
head camera (organisers' D435i, robot in home pose) -> position estimate (perceive.py) -> the arm aims there with the object's best posture
(grasp_postures.json) -> close to the cap, lift 10 cm. Reports visible / perception error / held per cell + a PNG map.
  py -3.11 g1/sim/coverage.py [--objects egg,stress_ball] [--workers 14]   -> data/g1sim/coverage/{coverage.json, <obj>.png}"""
import argparse, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "g1"))
OUT = os.path.join(ROOT, "data", "g1sim", "coverage")
XS = np.round(np.arange(0.20, 0.61, 0.05), 3); YS = np.round(np.arange(-0.40, 0.21, 0.05), 3)


def see(args):
    obj, spot = args
    import mujoco, demo_e2e as D, perceive as PC
    m, d = D.build(obj); kh = D.Kin()
    jq = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j): m.jnt_qposadr[j] for j in range(m.njnt)}
    for n, v in kh.a.q.items(): d.qpos[jq[n]] = v
    ob = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "obj"); a = m.jnt_qposadr[m.body_jntadr[ob]]
    p = kh.base + np.array([spot[0], spot[1], D.COUNTER_Z + D.half_h(obj)])
    d.qpos[a:a + 3] = p; d.qpos[a + 3:a + 7] = D.obj_quat(obj); mujoco.mj_forward(m, d)
    rgb, dm, mk = PC.render_head(m, d, seg_geom=mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "obj_g"))
    ph, info = PC.locate(rgb, dm, PC.cam_pose(m, d), obj, D.OBJECTS[obj]["size"][0], z_plane=p[2], mask=mk)
    return None if ph is None else (ph - p).tolist()


def main():
    import multiprocessing as mp, grasp_search as GS
    ap = argparse.ArgumentParser(); ap.add_argument("--objects", default="egg,stress_ball"); ap.add_argument("--workers", type=int, default=14); a = ap.parse_args()
    best = json.load(open(os.path.join(HERE, "grasp_postures.json"))); os.makedirs(OUT, exist_ok=True); out = {}
    with mp.Pool(a.workers) as pool:
        for obj in a.objects.split(","):
            b = best[obj]["best"]; spots = [(float(x), float(y)) for x in XS for y in YS]
            errs = pool.map(see, [(obj, s) for s in spots])
            jobs = [(obj, b["posture"], tuple(np.array(b["aim"]) - np.array([e[0], e[1], 0.0])) if e else b["aim"], s) for s, e in zip(spots, errs)]
            # the robot aims at the SEEN position: equivalent to the true object displaced by -error relative to the aim
            res = pool.map(GS.trial, jobs)
            cells = [{"x": s[0], "y": s[1], "visible": e is not None, "err_cm": None if e is None else round(100 * float(np.hypot(e[0], e[1])), 2),
                      "lift_cm": r["lift_cm"], "peak_N": r["peak_N"], "held": e is not None and GS.held(obj, r), "why": r["reason"]} for s, e, r in zip(spots, errs, res)]
            out[obj] = cells
            n_vis = sum(c["visible"] for c in cells); n_held = sum(c["held"] for c in cells); n_reach = sum(c["why"] == "" for c in cells)
            print(obj, f"cells {len(cells)} visible {n_vis} reachable {n_reach} held {n_held}", flush=True)
            import cv2
            img = np.full((len(XS) * 40 + 60, len(YS) * 40 + 20, 3), 255, np.uint8)
            for c in cells:
                i = list(XS).index(c["x"]); j = list(YS).index(c["y"]); col = (60, 180, 60) if c["held"] else ((60, 60, 220) if c["visible"] and c["why"] == "" else ((180, 180, 180) if c["visible"] else (40, 40, 40)))
                y0 = (len(XS) - 1 - i) * 40 + 10; x0 = (len(YS) - 1 - j) * 40 + 10; cv2.rectangle(img, (x0, y0), (x0 + 36, y0 + 36), col, -1)
            cv2.putText(img, f"{obj}: verde=presa ok, rosso=vista ma persa, grigio=fuori portata, nero=non vista", (10, img.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 0), 1)
            cv2.imwrite(os.path.join(OUT, f"{obj}.png"), img)
    json.dump(out, open(os.path.join(OUT, "coverage.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
