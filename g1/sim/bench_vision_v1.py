"""Bench for g1/perception_v1.perceive on MuJoCo G1 head RGB-D renders (egg + empty can on the counter, known positions).
  py -3.11 g1/sim/bench_vision_v1.py [--n 12] [--engine ai|g1] [--vlm nemotron,gemma] [--save-frames data/g1sim/v1_frames.npz]
Reports per object: label correct?, xy error (cm), depth_ok; and the hand assignment. Sim objects are plain shapes (white ellipsoid, gold
cylinder): a VLM may not call them egg/can, so the VLM path is measured separately and honestly; the default run is geometry+colour only.
Camera = organisers' head camera (same T_pelvis_optical as calibration.yaml, sim intrinsics fx=fy=615, cx 320, cy 240)."""
import argparse, json, os, sys
import numpy as np, mujoco

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [HERE, ROOT]
import demo_e2e as D, perceive as PC, teleop_multi as TM
from g1.perception_v1 import perceive, perceive_with_ai, assign, pinhole_pixel_to_pelvis, robot_mask
import arm_ik

K_SIM = np.array([[PC.FX, 0, PC.CX], [0, PC.FX, PC.CY], [0, 0, 1.0]])


def scene():
    m, d = TM.build_multi([("egg", None), ("can_empty", None)]); kin = D.Kin()
    jq = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j): m.jnt_qposadr[j] for j in range(m.njnt)}
    for nm, v in kin.a.q.items():
        if nm in jq: d.qpos[jq[nm]] = v
    return m, d, kin


def place(m, d, kin, layout):
    gt = {}
    for obj, (x, y) in layout.items():
        b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, f"obj_{obj}"); a = m.jnt_qposadr[m.body_jntadr[b]]
        p = np.array([x, y, D.COUNTER_Z + D.half_h(obj)]); d.qpos[a:a + 3] = kin.base + p; d.qpos[a + 3:a + 7] = D.obj_quat(obj); gt[obj] = p
    mujoco.mj_forward(m, d)
    pos, R = PC.cam_pose(m, d); T = np.eye(4); T[:3, :3] = R @ np.diag([1, -1, -1]); T[:3, 3] = pos - kin.base   # MuJoCo cam -> optical, pelvis frame
    rgb, dep = PC.render_head(m, d)
    return rgb, dep, T, gt


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=12); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--vlm", default=""); ap.add_argument("--no-self-mask", action="store_true"); ap.add_argument("--engine", default="ai", choices=["ai", "g1"]); ap.add_argument("--save-frames", default=os.path.join(ROOT, "data", "g1sim", "v1_frames.npz"))
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "g1sim", "bench_vision_v1.json")); a = ap.parse_args()
    vlm = [b for b in a.vlm.split(",") if b]
    m, d, kin = scene(); rng = np.random.default_rng(a.seed)
    layouts = [{"egg": (0.35, -0.15), "can_empty": (0.35, 0.15)}]       # the V1 demo layout (same as the CLI defaults)
    while len(layouts) < a.n:
        layouts.append({"egg": (rng.uniform(0.28, 0.45), rng.uniform(-0.25, -0.08)), "can_empty": (rng.uniform(0.28, 0.45), rng.uniform(0.08, 0.25))})
    rows = []
    for i, lay in enumerate(layouts):
        rgb, dep, T, gt = place(m, d, kin, lay)
        if i == 0 and a.save_frames:
            os.makedirs(os.path.dirname(a.save_frames), exist_ok=True); np.savez_compressed(a.save_frames, rgb=rgb, depth=dep, K=K_SIM, T=T, arm_q=np.array([kin.a.q[n] for n in arm_ik.ARM_NAMES]))
            import cv2; cv2.imwrite(a.save_frames.replace(".npz", ".jpg"), rgb[:, :, ::-1])
        armq = [kin.a.q[n] for n in arm_ik.ARM_NAMES]
        sm = robot_mask(armq, None, K_SIM, T)(dep) if not a.no_self_mask else None
        res = (perceive_with_ai if a.engine == "ai" else perceive)(rgb, dep, pinhole_pixel_to_pelvis(K_SIM, T), vlm=vlm, self_mask=sm); asg = assign(res["objects"])
        for obj, side in (("egg", "right"), ("can_empty", "left")):
            o = asg[side]
            row = {"layout": i, "object": obj, "hand": side, "gt_xy": np.round(gt[obj][:2], 3).tolist(), "found": o is not None}
            if o:
                row.update(label=o["label"], label_ok=o["label"] == obj, cap=o["cap"], depth_ok=o["depth_ok"],
                           xy_err_cm=round(100 * float(np.hypot(*(np.array(o["p_pelvis"][:2]) - gt[obj][:2]))), 2),
                           z_err_cm=round(100 * float(o["p_pelvis"][2] - gt[obj][2]), 2), votes=o["votes"])
            rows.append(row)
        print(i, f"table_z {res['table_z']} n_obj {len(res['objects'])} {res['t_s']} s |",
              " | ".join(f"{r['object']}: {r.get('label')} cap {r.get('cap')} err {r.get('xy_err_cm')} cm ok {r.get('depth_ok')}" for r in rows[-2:]), flush=True)
    summ = {}
    for obj in ("egg", "can_empty"):
        rr = [r for r in rows if r["object"] == obj]; e = np.array([r.get("xy_err_cm", np.nan) for r in rr], float)
        summ[obj] = {"n": len(rr), "found": sum(r["found"] for r in rr), "label_ok": sum(bool(r.get("label_ok")) for r in rr),
                     "depth_ok": sum(bool(r.get("depth_ok")) for r in rr), "xy_err_cm_median": round(float(np.nanmedian(e)), 2) if np.isfinite(e).any() else None,
                     "xy_err_cm_max": round(float(np.nanmax(e)), 2) if np.isfinite(e).any() else None}
    print(json.dumps({"engine": a.engine, "vlm": vlm, "summary": summ}, indent=1))
    json.dump({"engine": a.engine, "vlm": vlm, "summary": summ, "rows": rows}, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
