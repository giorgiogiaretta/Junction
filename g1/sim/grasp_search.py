"""Per-object grasp POSTURE + AIM search for the G1 Dex3 right hand in MuJoCo (multiprocessing).
  py -3.11 g1/sim/grasp_search.py [--objects egg,stress_ball,can_empty] [--workers 14]  -> g1/sim/grasp_postures.json, data/g1sim/search/*.png
Candidates: a grid of right-arm postures filtered by geometry (squeeze axis thumb->fingers nearly horizontal; palm above the pinch so the hand
can come down from above; for the can: fingers pointing down = TOP grasp around the upper part). For each candidate the arm is moved by IK
(orientation kept) so the pinch is at object + aim, the object rests on the counter, the hand closes to the object's cap in 2 s, lifts 10 cm
in 1 s and holds 1 s. Held = object up >= 7 cm. Egg also needs peak force (0.1 s mean) < 20 N. Robustness of the best ones = fraction of
held trials when the aim is perturbed by +-1 cm in x, y, z. Organisers' rules checked on every pose: wrist/palm above pelvis z 0.03, box, filter.
Assumptions as in demo_e2e.py (servo gains, friction, break thresholds, object sizes)."""
import argparse, itertools, json, os, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "g1"))
AIM_Z = {"egg": (-0.02, -0.01, 0.0), "stress_ball": (-0.02, -0.01, 0.0, 0.01), "can_empty": (-0.02, 0.0, 0.02)}   # can: SIDE grasp around its middle (like the glove takes)   # pinch height vs object centre
GRID = dict(sp=(-0.9, -0.6, -0.3), el=(0.0, 0.4, 0.8, 1.2), wr=(-1.57, -0.8, 0.0, 0.8), wp=(-0.5, 0.0, 0.5, 1.0), wy=(-0.5, 0.0, 0.5))
_CACHE = {}


def _setup(obj):
    if obj in _CACHE: return _CACHE[obj]
    import mujoco, demo_e2e as D
    from robot.g1_dex3 import G1Dex3Retargeter
    m, d = D.build(obj)
    names = [j["joint"] for j in G1Dex3Retargeter().joints]
    act = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, m.actuator_trnid[a, 0]): a for a in range(m.nu)}
    jq = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j): m.jnt_qposadr[j] for j in range(m.njnt)}
    ob = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "obj"); og = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "obj_g")
    _CACHE[obj] = (D, m, d, names, act, jq, m.jnt_qposadr[m.body_jntadr[ob]], og)
    return _CACHE[obj]


def posture_q(c):
    return {"right_shoulder_pitch_joint": c[0], "right_shoulder_roll_joint": -0.25, "right_shoulder_yaw_joint": 0.0, "right_elbow_joint": c[1],
            "right_wrist_roll_joint": c[2], "right_wrist_pitch_joint": c[3], "right_wrist_yaw_joint": c[4]}


def geometry(obj, c):
    """squeeze axis, palm height above the pinch, finger direction for one posture (hand half-closed to the cap)."""
    import demo_e2e as D
    from robot.g1_dex3 import G1Dex3Retargeter
    k = D.Kin(); rt = G1Dex3Retargeter(max_closure=1.0); cap = D.PROFILE[obj]["cap"]
    for _ in range(30): hq = rt.step(right=[0.5 * cap] * 3 + [0, 0])
    for n, v in posture_q(c).items(): k.a.q[n] = v
    k.a.apply(hq)
    th = k.tip("right_hand_thumb_2_link"); fi = 0.5 * (k.tip("right_hand_index_1_link") + k.tip("right_hand_middle_1_link"))
    ax = (fi - th) / (np.linalg.norm(fi - th) + 1e-9); pin = k.pinch(); palm = k.palm()
    return abs(ax[2]), float(palm[2] - pin[2]), float(np.linalg.norm(fi - th))


def trial(args):
    """one physics trial -> dict(lift_cm, peak_N, ok_safety)"""
    obj, c, aim = args[:3]; spot = args[3] if len(args) > 3 else (0.35, -0.15)
    import mujoco
    D, m, d, names, act, jq, oa, og = _setup(obj)
    from robot.g1_dex3 import G1Dex3Retargeter
    cap = D.PROFILE[obj]["cap"]; aim = np.array(aim)
    k = D.Kin(); rt0 = G1Dex3Retargeter(max_closure=1.0)
    for _ in range(30): hq0 = rt0.step(right=[0.5 * cap] * 3 + [0, 0])
    for n, v in posture_q(c).items(): k.a.q[n] = v
    k.a.apply(hq0); ee = k.a.ee["right"]; w0 = k.a.d.xpos[ee].copy(); Rg = k.a.d.xmat[ee].reshape(3, 3).copy(); pin0 = k.pinch().copy()
    top = k.base[2] + D.COUNTER_Z; obj_c = np.array([k.base[0] + spot[0], k.base[1] + spot[1], top + D.half_h(obj)])   # object on the mat, right of centre
    wt = w0 + (obj_c + aim - pin0)
    for _ in range(120): k.a.solve("right", wt, Rg)
    if np.linalg.norm(k.a.d.xpos[ee] - wt) > 0.008 or D.checks(k): return {"lift_cm": -1.0, "peak_N": 0.0, "reason": "unreachable/unsafe"}
    q_grasp = k.a.arm_q(); path = []
    for s in range(30):
        k.a.solve("right", wt + np.array([0, 0, 0.10 * (s + 1) / 30]), Rg); path.append(k.a.arm_q())
        if D.checks(k): return {"lift_cm": -1.0, "peak_N": 0.0, "reason": "unsafe lift"}
    mujoco.mj_resetData(m, d)
    for n, v in zip(D.arm_ik.ARM_NAMES, q_grasp): d.qpos[jq[n]] = v; d.ctrl[act[n]] = v
    for n in names: d.ctrl[act[n]] = 0.0
    d.qpos[oa:oa + 3] = obj_c; d.qpos[oa + 3:oa + 7] = D.obj_quat(obj); mujoco.mj_forward(m, d)
    if any(og in (cn.geom1, cn.geom2) and cn.dist < -0.002 for cn in d.contact[:d.ncon]): return {"lift_cm": -1.0, "peak_N": 0.0, "reason": "starts in collision"}
    hb = {b for b in range(m.nbody) if "right_hand" in (mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_BODY, b) or "")}
    spt = int(round(1 / 30 / m.opt.timestep)); rt = G1Dex3Retargeter(max_closure=1.0); F = []; f6 = np.zeros(6)
    for t in range(60 + 60):
        if t < 60: hq = rt.step(right=[cap] * 3 + [0, 0]); [d.ctrl.__setitem__(act[n], v) for n, v in zip(names, hq)]
        else: [d.ctrl.__setitem__(act[n], v) for n, v in zip(D.arm_ik.ARM_NAMES, path[min(t - 60, 29)])]
        acc = 0.0
        for _ in range(spt):
            mujoco.mj_step(m, d)
            for i in range(d.ncon):
                cn = d.contact[i]
                if og in (cn.geom1, cn.geom2) and m.geom_bodyid[cn.geom2 if cn.geom1 == og else cn.geom1] in hb: mujoco.mj_contactForce(m, d, i, f6); acc += abs(f6[0])
        F.append(acc / spt)
    pk = float(max(np.convolve(F, np.ones(3) / 3, mode="valid"))) if len(F) > 3 else 0.0
    return {"lift_cm": round(100 * float(d.qpos[oa + 2] - obj_c[2]), 1), "peak_N": round(pk, 1), "reason": ""}


def held(obj, r): return r["lift_cm"] >= 7.0 and (obj != "egg" or r["peak_N"] < 20.0)


def search(obj, pool):
    t0 = time.time()
    cands = list(itertools.product(*GRID.values()))
    geo = pool.map(_geo_star, [(obj, c) for c in cands])
    keep = []
    for c, (axz, palm_up, span) in zip(cands, geo):
        if axz > 0.3: continue
        if obj == "can_empty" and abs(palm_up) > 0.03: continue     # side grasp: palm beside the can at pinch height (glove takes 70-73, 85-89)
        if obj != "can_empty" and palm_up < 0.03: continue
        keep.append((axz + 0.5 * max(0, 0.06 - palm_up), c))
    keep = [c for _, c in sorted(keep)[:24]]
    aims = [(dx, dy, dz) for dx in (-0.015, 0.0, 0.015) for dy in (-0.015, 0.0, 0.015) for dz in AIM_Z[obj]]
    jobs = [(obj, c, a) for c in keep for a in aims]
    res = pool.map(trial, jobs)
    rows = [{"posture": c, "aim": a, **r} for (_, c, a), r in zip(jobs, res)]
    good = sorted([r for r in rows if held(obj, r)], key=lambda r: (r["peak_N"] if obj == "egg" else -r["lift_cm"]))[:6]
    best = None
    for g in good:                                                   # robustness: +-1 cm on each axis
        nb = [tuple(np.array(g["aim"]) + np.array(v)) for v in ((0.01, 0, 0), (-0.01, 0, 0), (0, 0.01, 0), (0, -0.01, 0), (0, 0, 0.01), (0, 0, -0.01))]
        rr = pool.map(trial, [(obj, g["posture"], a) for a in nb])
        g["robust"] = round(sum(held(obj, r) for r in rr) / len(rr), 2); g["neighbours"] = rr
        if best is None or (g["robust"], -g["peak_N"]) > (best["robust"], -best["peak_N"]): best = g
    return {"object": obj, "candidates": len(keep), "trials": len(rows), "held": sum(held(obj, r) for r in rows), "best": best,
            "runtime_s": round(time.time() - t0, 1)}


def _geo_star(a): return geometry(*a)


def main():
    import multiprocessing as mp
    ap = argparse.ArgumentParser(); ap.add_argument("--objects", default="egg,stress_ball,can_empty"); ap.add_argument("--workers", type=int, default=14)
    a = ap.parse_args(); out_p = os.path.join(HERE, "grasp_postures.json")
    out = json.load(open(out_p)) if os.path.exists(out_p) else {}
    with mp.Pool(a.workers) as pool:
        for obj in a.objects.split(","):
            r = search(obj, pool); out[obj] = r
            b = r["best"]
            print(obj, "held", r["held"], "/", r["trials"], "| best", None if not b else {k: b[k] for k in ("posture", "aim", "lift_cm", "peak_N", "robust")}, "|", r["runtime_s"], "s", flush=True)
            json.dump(out, open(out_p, "w"), indent=1, default=float)


if __name__ == "__main__":
    main()
