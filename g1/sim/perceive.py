"""Head-camera object localisation in the MuJoCo G1 scene: the same camera as the real robot (D435i at the URDF d435_link, 640x480,
fx = fy = 615, cx 320, cy 240, organisers' INTERFACE.md), RGB + aligned depth (mm, 0 = invalid), exactly the obs the policy receives.
  rgb, depth_mm = render_head(m, d)            # (480, 640, 3) uint8 RGB, (480, 640) uint16
  p_pelvis, info = locate(rgb, depth_mm, cam_pose, obj)   # object centre estimate (world frame here; pelvis frame on the robot)
Segmentation in sim = colour of the simulated object (egg white, ball orange, can gold). On the robot this step is Tommaso's detector (bbox);
the rest (depth median in the central part of the mask -> back-projection -> push by the object radius along the ray, z snapped to the counter)
is the same code. Also a test bench for any locate(): `py -3.11 g1/sim/perceive.py` prints the error vs ground truth on random placements."""
import json, os, sys
import numpy as np, mujoco, cv2

W, H, FX, CX, CY = 640, 480, 615.0, 320.0, 240.0
FOVY = float(np.degrees(2 * np.arctan(H / 2 / FX)))      # 42.6 deg: same intrinsics as the organisers' head camera
COLORS = {"egg": ((0.9, 0.85, 0.75), (1.0, 1.0, 1.0)), "stress_ball": ((0.8, 0.25, 0.0), (1.0, 0.65, 0.25)), "can_empty": ((0.65, 0.5, 0.15), (0.95, 0.85, 0.5))}


def render_head(m, d, cam="head_cam", seg_geom=None):
    """RGB, depth (mm) and, if seg_geom is given, the pixel mask of that geom (= a perfect 2D detector; on the robot: Tommaso's bbox/mask)."""
    m.cam_fovy[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_CAMERA, cam)] = FOVY
    r = mujoco.Renderer(m, H, W); r.update_scene(d, cam); rgb = r.render().copy()
    r.enable_depth_rendering(); r.update_scene(d, cam); dep = r.render().copy(); r.disable_depth_rendering()
    mk = None
    if seg_geom is not None:
        r.enable_segmentation_rendering(); r.update_scene(d, cam); sg = r.render().copy(); r.disable_segmentation_rendering()
        mk = (sg[:, :, 0] == seg_geom) & (sg[:, :, 1] == int(mujoco.mjtObj.mjOBJ_GEOM))
    r.close()
    dm = np.clip(dep * 1000.0, 0, 65535).astype(np.uint16); dm[(dep <= 0) | (dep > 6.0)] = 0
    return (rgb, dm, mk) if seg_geom is not None else (rgb, dm)


def cam_pose(m, d, cam="head_cam"):
    i = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_CAMERA, cam)
    return d.cam_xpos[i].copy(), d.cam_xmat[i].reshape(3, 3).copy()   # MuJoCo camera: x right, y up, looks along -z


def mask_for(rgb, obj):
    lo, hi = (np.array(c) * 255 for c in COLORS[obj])
    mk = np.all((rgb >= lo) & (rgb <= hi), axis=2).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(mk)
    if n <= 1: return None
    k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    return (lab == k) if st[k, cv2.CC_STAT_AREA] > 30 else None


def locate(rgb, depth_mm, pose, obj, radius, z_plane=None, mask=None):
    """mask (given, or by colour) -> central half of the mask (avoid edges/mixed depth) -> median depth -> back-project -> push by `radius` along the ray."""
    mk = mask if mask is not None else mask_for(rgb, obj)
    if mk is None or mk.sum() < 30: return None, {"error": "object not visible"}
    vs, us = np.nonzero(mk)
    uc, vc = np.median(us), np.median(vs)
    core = mk & (np.abs(np.arange(W)[None, :] - uc) < 0.25 * (us.max() - us.min() + 1)) & (np.abs(np.arange(H)[:, None] - vc) < 0.25 * (vs.max() - vs.min() + 1))
    dz = depth_mm[core & (depth_mm > 0)]
    if len(dz) < 5: return None, {"error": "no valid depth on the object"}
    z = float(np.median(dz)) / 1000.0
    ray_cv = np.array([(uc - CX) / FX, (vc - CY) / FX, 1.0])          # OpenCV optical frame: x right, y down, z forward
    p_cv = ray_cv * z                                                   # MuJoCo depth = distance along the optical axis
    p_cam = np.array([p_cv[0], -p_cv[1], -p_cv[2]])                     # -> MuJoCo camera frame
    pos, R = pose; p_surf = pos + R @ p_cam
    ray_w = R @ np.array([ray_cv[0], -ray_cv[1], -1.0]); ray_w /= np.linalg.norm(ray_w)
    p = p_surf + radius * ray_w
    if z_plane is not None: p[2] = z_plane
    return p, {"pixel": [round(float(uc), 1), round(float(vc), 1)], "depth_m": round(z, 4), "mask_px": int(mk.sum())}


def bench(n=20, seed=0):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import demo_e2e as D
    rng = np.random.default_rng(seed); out = {}
    for obj in ("egg", "stress_ball", "can_empty"):
        m, d = D.build(obj); kin = D.Kin()
        jq = {mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_JOINT, j): m.jnt_qposadr[j] for j in range(m.njnt)}
        for nm, v in kin.a.q.items(): d.qpos[jq[nm]] = v                # organisers' home pose
        ob = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "obj"); a = m.jnt_qposadr[m.body_jntadr[ob]]
        errs = []
        for _ in range(n):
            p = kin.base + np.array([rng.uniform(0.25, 0.55), rng.uniform(-0.30, 0.10), D.COUNTER_Z + D.half_h(obj)])
            d.qpos[a:a + 3] = p; d.qpos[a + 3:a + 7] = D.obj_quat(obj); mujoco.mj_forward(m, d)
            og = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "obj_g"); rgb, dm, mk = render_head(m, d, seg_geom=og)
            r = D.OBJECTS[obj]["size"][0]
            ph, info = locate(rgb, dm, cam_pose(m, d), obj, r, z_plane=kin.base[2] + D.COUNTER_Z + D.half_h(obj), mask=mk)
            errs.append(np.nan if ph is None else float(np.linalg.norm((ph - p)[:2])))
        e = np.array(errs); out[obj] = {"n": n, "visible": int(np.isfinite(e).sum()), "xy_err_cm_median": round(100 * float(np.nanmedian(e)), 2),
                                        "xy_err_cm_max": round(100 * float(np.nanmax(e)), 2)}
        print(obj, out[obj])
    return out


if __name__ == "__main__":
    json.dump(bench(), open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "g1sim", "perceive_bench.json"), "w"), indent=1)
