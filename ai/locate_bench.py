"""Run ai.locate on Giorgio's MuJoCo head-camera bench (g1/sim/perceive.py, same scene and random placements) and print the xy error.
  py -3.11 -m ai.locate_bench [--n 20]        # needs mujoco + cv2 + data/g1sim/assets_g1 (g1/sim/g1_sim.py downloads them)
Three modes per object: 'mask' (perfect sim segmentation = ideal detector), 'bbox' (box of that mask = what a VLM/detector gives),
'colour' (no help: ai.locate's own white/orange blobs). Writes data/g1sim/locate_bench.json. Frame here = MuJoCo world (pelvis on the robot)."""
import argparse, json, os, sys
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "g1", "sim"))
from ai.locate import locate, camera_point


def pixel_to_world(pose):
    """ai.locate wants f(u, v, depth_mm) -> 3D point. Optical frame (x right, y down, z fwd) -> MuJoCo camera (x right, y up, -z fwd) -> world."""
    pos, R = pose
    def f(u, v, d):
        x, y, z = camera_point(u, v, d)
        return (pos + R @ np.array([x, -y, -z])).tolist()
    return f


def run(n=20, seed=0):
    import mujoco, perceive as P, demo_e2e as D
    rng = np.random.default_rng(seed); out = {}
    for obj in ("egg", "stress_ball", "can_empty"):
        m, d = D.build(obj); kin = D.Kin()
        jq = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j): m.jnt_qposadr[j] for j in range(m.njnt)}
        for nm, v in kin.a.q.items(): d.qpos[jq[nm]] = v
        ob = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "obj"); a = m.jnt_qposadr[m.body_jntadr[ob]]
        og = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "obj_g")
        errs = {"mask": [], "bbox": [], "colour": []}; zt = kin.base[2] + D.COUNTER_Z
        for _ in range(n):
            p = kin.base + np.array([rng.uniform(0.25, 0.55), rng.uniform(-0.30, 0.10), D.COUNTER_Z + D.half_h(obj)])
            d.qpos[a:a + 3] = p; d.qpos[a + 3:a + 7] = D.obj_quat(obj); mujoco.mj_forward(m, d)
            rgb, dm, mk = P.render_head(m, d, seg_geom=og); f = pixel_to_world(P.cam_pose(m, d))
            label = "can" if obj.startswith("can") else obj
            vs, us = np.nonzero(mk) if mk.sum() else ([0], [0])
            runs = {"mask": dict(mask=mk, label=label), "bbox": dict(bbox=[min(us), min(vs), max(us), max(vs)], label=label), "colour": {}}
            for mode, kw in runs.items():
                if mode != "colour" and mk.sum() < 30: errs[mode].append(np.nan); continue
                r = locate(rgb, dm, f, table_z=zt, **kw)
                ok = r["p_pelvis"] is not None and (mode != "colour" or r["object"] == label)
                errs[mode].append(float(np.linalg.norm((np.array(r["p_pelvis"]) - p)[:2])) if ok else np.nan)
        out[obj] = {}
        for mode, e in errs.items():
            e = np.array(e); ok = np.isfinite(e)
            out[obj][mode] = {"n": n, "found": int(ok.sum()), "xy_cm_median": round(100 * float(np.median(e[ok])), 2) if ok.any() else None,
                              "xy_cm_max": round(100 * float(np.max(e[ok])), 2) if ok.any() else None,
                              "within_1cm": int((e[ok] <= 0.01).sum())}
        print(obj, json.dumps(out[obj]))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=20); a = ap.parse_args()
    res = run(a.n); path = os.path.join(ROOT, "data", "g1sim", "locate_bench.json"); os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(res, open(path, "w"), indent=1); print("wrote", path)
