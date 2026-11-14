"""V1 perception: ONE call at the first valid head frame -> every object on the table with label, closure cap and pelvis position.
Composes Tommaso's ai/ modules without editing them (no single perceive() on main yet, board 2026-11-14 16:56):
  segment   depth above the table plane (any colour: the real empty can is not gold), connected components
  label     fragile-first vote of (a) a local geometry+colour rule (height above table, white / orange fraction) and (b) ai.recognize VLM
            backends on a crop of each object (optional, needs keys; a dead endpoint is an ok=False vote after the timeout)
  position  ai.locate.locate(..., mask=component, table_z=plane) -> object centre in the pelvis frame
  perceive(head_rgb, head_depth_mm, pixel_to_pelvis, vlm=()) -> {"table_z", "objects": [...], "t_s"}
  assign(objects, overrides) -> {"right": obj|None, "left": obj|None}: each hand takes the nearest object on its side (pelvis y<0 = right)
Caps: egg 0.70, can_empty = g1/object_profiles.json can.max_closure (0.45: an empty can crushes, irreversible; board 17:50),
stress_ball via ai.object_profile.cap_for_votes, anything else / disagreement -> unknown 0.68. Sizes and thresholds are nominal; tested on MuJoCo renders only (g1/sim/bench_vision_v1.py)."""
import io, os, time
import numpy as np

def _can_cap(default=0.45):
    try:
        import json; return float(json.load(open(os.path.join(os.path.dirname(__file__), "object_profiles.json")))["can"]["max_closure"])
    except Exception: return default
CAP = {"egg": 0.70, "can_empty": _can_cap(), "stress_ball": 0.70, "unknown": 0.68}
WORK = dict(x=(0.12, 0.80), y=(-0.55, 0.55), z=(-0.40, 0.45))   # pelvis-frame box where objects can be
MIN_ABOVE, MAX_ABOVE = 0.012, 0.30                                 # object pixels: this far above the table plane (m)
MIN_AREA, MAX_FOOT, MERGE = 150, 0.20, 0.06                                     # px, m (bigger footprint = arm, box, person)
CAN_MIN_H, CAN_MAX_H, CAN_MAX_FOOT = 0.09, 0.20, 0.09                                                   # standing can 146 mm; egg 43 mm lying, ball 65 mm
SHOULDER = {"right": (0.0, -0.15), "left": (0.0, 0.15)}


def head_pixel_to_pelvis(repo=None):
    """Organisers' calibration (aaltonomous.interface.calibration, PROVISIONAL extrinsics): vectorised (u, v, depth_mm) -> pelvis m."""
    from aaltonomous.interface.calibration import Calibration
    cal = Calibration.load()
    return lambda u, v, d: cal.pixel_to_pelvis("head", u, v, d)


def pinhole_pixel_to_pelvis(K, T):
    """Same maths as Calibration.pixel_to_pelvis for a given 3x3 K and 4x4 T_pelvis_optical (sim bench / test frames)."""
    K = np.asarray(K, float); T = np.asarray(T, float)
    def f(u, v, d):
        z = np.asarray(d, float) / 1000.0
        p = np.stack([(np.asarray(u, float) - K[0, 2]) / K[0, 0] * z, (np.asarray(v, float) - K[1, 2]) / K[1, 1] * z, z], -1)
        return p @ T[:3, :3].T + T[:3, 3]
    return f


def available_vlm():
    """Backends whose credentials are present in the environment (values never read or logged)."""
    e = os.environ; out = []
    if e.get("VERDA_INFERENCE_KEY") or e.get("NVIDIA_API_KEY"): out.append("nemotron")
    if e.get("GEMMA_BASE_URL") or e.get("GEMINI_API_KEY") or e.get("GOOGLE_API_KEY"): out.append("gemma")
    return out


import threading
_TLS = threading.local()   # renderer + model per thread: a MuJoCo GL context only works in the thread that created it


def robot_mask(arm_q, hand_q, K, T, shape=(480, 640), dilate=7, margin=0.03):
    """Pixels where the G1's own body is (kinematic model at the MEASURED arm/hand joints, rendered as depth from the camera pose
    T_pelvis_optical with intrinsics K; principal point applied as an image shift). Returns depth_mm -> bool mask: robot rendered at the
    pixel AND the measured depth is not nearer than the robot by more than `margin` (= what the camera sees there is the robot).
    The organisers' home pose puts both hands in the head camera view, right over the V1 objects."""
    import cv2, mujoco, sys
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path: sys.path.insert(0, here)
    import arm_ik
    H, W = shape
    _ARMS = _TLS.__dict__
    if "a" not in _ARMS:
        a = arm_ik.G1Arms(with_cam=False); a.m.vis.global_.offwidth, a.m.vis.global_.offheight = W, H
        base = a.d.xpos[mujoco.mj_name2id(a.m, mujoco.mjtObj.mjOBJ_BODY, "pelvis")].copy()
        _ARMS.update(a=a, base=base, r=mujoco.Renderer(a.m, H, W))
    a, base, r = _ARMS["a"], _ARMS["base"], _ARMS["r"]
    a.q.update({n: float(v) for n, v in zip(arm_ik.ARM_NAMES, np.asarray(arm_q, float))}); a.apply(None if hand_q is None else list(hand_q))
    K = np.asarray(K, float); T = np.asarray(T, float)
    a.m.vis.global_.fovy = float(np.degrees(2 * np.arctan(H / 2 / K[1, 1])))
    fwd = T[:3, 2]; cam = mujoco.MjvCamera(); cam.type = mujoco.mjtCamera.mjCAMERA_FREE; cam.distance = 1.0
    cam.lookat[:] = base + T[:3, 3] + fwd
    cam.azimuth = float(np.degrees(np.arctan2(fwd[1], fwd[0]))); cam.elevation = float(np.degrees(np.arcsin(np.clip(fwd[2], -1, 1))))
    opt = mujoco.MjvOption(); r.enable_depth_rendering(); r.update_scene(a.d, cam, opt); zr = r.render().copy(); r.disable_depth_rendering()
    zr[(zr <= 0) | (zr > 5.0)] = 0
    M = np.float32([[1, 0, K[0, 2] - W / 2], [0, 1, K[1, 2] - H / 2]])
    zr = cv2.warpAffine(zr.astype(np.float32), M, (W, H), flags=cv2.INTER_NEAREST, borderValue=0)
    def mask(depth_mm):
        z = np.asarray(depth_mm, float) / 1000.0
        out = (zr > 0) & ((z == 0) | (z >= zr - margin))
        return cv2.dilate(out.astype(np.uint8), np.ones((dilate, dilate), np.uint8)) > 0
    return mask


def _table_plane(P, valid):
    """Mode of z over the workspace (5 mm bins): the dominant horizontal surface = the table."""
    z = P[..., 2][valid]
    if z.size < 1000: return None
    h, edges = np.histogram(z, bins=np.arange(WORK["z"][0], WORK["z"][1], 0.005))
    k = int(np.argmax(h)); sel = z[(z >= edges[k] - 0.005) & (z < edges[k + 1] + 0.005)]
    return float(np.median(sel))


def segment(rgb, depth, p2p, self_mask=None):
    import cv2
    depth = np.asarray(depth); H, W = depth.shape
    vv, uu = np.mgrid[0:H, 0:W]
    P = np.asarray(p2p(uu.astype(float), vv.astype(float), depth.astype(float)), float).reshape(H, W, 3)
    ok = depth > 0
    inw = ok & (P[..., 0] > WORK["x"][0]) & (P[..., 0] < WORK["x"][1]) & (np.abs(P[..., 1]) < WORK["y"][1])
    tz = _table_plane(P, inw)
    if tz is None: return None, [], P
    above = inw & (P[..., 2] > tz + MIN_ABOVE) & (P[..., 2] < tz + MAX_ABOVE)
    if self_mask is not None: above &= ~np.asarray(self_mask, bool)
    m8 = cv2.morphologyEx(above.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m8, connectivity=8)
    parts = [lab == i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= MIN_AREA // 3]
    # one object split by an occluder (a finger across the can) -> merge parts whose xy centres are < MERGE apart
    cen = [np.median(P[mk][:, :2], 0) for mk in parts]; grp = list(range(len(parts)))
    for i in range(len(parts)):
        for j in range(i):
            if np.hypot(*(cen[i] - cen[j])) < MERGE: grp = [grp[j] if g == grp[i] else g for g in grp]
    comps = []
    for gi in sorted(set(grp)):
        mk = np.any([parts[k] for k in range(len(parts)) if grp[k] == gi], axis=0)
        if mk.sum() < MIN_AREA: continue
        Q = P[mk]
        foot = float(max(np.ptp(Q[:, 0]), np.ptp(Q[:, 1])))
        if foot > MAX_FOOT: continue
        vs, us = np.nonzero(mk)
        comps.append({"mask": mk, "height": float(np.percentile(Q[:, 2], 97) - tz), "foot": foot,
                      "xy_top": np.median(Q[:, :2], 0).tolist(), "area": int(mk.sum()), "parts": int(sum(g == gi for g in grp)),
                      "bbox": [int(us.min()), int(vs.min()), int(us.max()), int(vs.max())]})
    return tz, comps, P


def geometry_vote(rgb, c):
    from ai.locate import colour_mask
    cm = colour_mask(np.asarray(rgb)); a = max(1, int(c["mask"].sum()))
    white = float((cm["egg"] & c["mask"]).sum()) / a; orange = float((cm["stress_ball"] & c["mask"]).sum()) / a
    h = c["height"]
    # can: tall, narrow (a 58 mm can; an egg merged with a can is wider) and not mostly white (egg) -> else unknown 0.68
    if CAN_MIN_H <= h <= CAN_MAX_H and c["foot"] <= CAN_MAX_FOOT and white < 0.3: lab, conf = "can_empty", 0.8
    elif orange > 0.5 and 0.04 <= h <= 0.08: lab, conf = "stress_ball", 0.7
    elif white > 0.5 and 0.025 <= h <= 0.065: lab, conf = "egg", 0.7
    elif orange < 0.3 and 0.02 <= h <= 0.065 and c["foot"] <= 0.08: lab, conf = "egg", 0.5   # egg-sized, not orange: fragile-first (shadowed egg)
    else: lab, conf = "unknown", None
    return {"name": "geometry", "object": lab, "confidence": conf, "ok": lab != "unknown",
            "why": f"h {100 * h:.1f} cm, white {white:.2f}, orange {orange:.2f}"}


def _crop_jpeg(rgb, bbox, pad=40):
    import cv2
    u0, v0, u1, v1 = bbox; H, W = rgb.shape[:2]
    crop = np.asarray(rgb)[max(0, v0 - pad):min(H, v1 + pad + 1), max(0, u0 - pad):min(W, u1 + pad + 1)]
    ok, buf = cv2.imencode(".jpg", crop[:, :, ::-1]); return buf.tobytes()


def _norm(label):
    try:
        from ai.object_profile import normalize
        k = normalize(label)
    except Exception: k = str(label)
    return {"can": "can_empty", "can_empty": "can_empty", "egg": "egg", "stress_ball": "stress_ball"}.get(k, "unknown")


def decide(votes, geo):
    """Fragile-first (ai.recognize.decide rule) on normalised labels; can full force needs the geometry vote."""
    ok = [dict(v, object=_norm(v["object"])) for v in votes if v.get("ok")]
    ok = [v for v in ok if v["object"] != "unknown"]
    if not ok: return "unknown", None, 0, "no recogniser gave a known label"
    if any(v["object"] == "egg" and (v["confidence"] is None or v["confidence"] >= 0.6) for v in ok):
        return "egg", None, sum(v["object"] == "egg" for v in ok), "fragile-first: a recogniser says egg"
    labels = {v["object"] for v in ok}
    if len(labels) > 1: return "unknown", None, 0, f"recognisers disagree {sorted(labels)}"
    lab = labels.pop(); cs = [v["confidence"] for v in ok if v["confidence"] is not None]
    return lab, (sum(cs) / len(cs) if cs else None), len(ok), "all known votes agree"


def cap_for(label, conf, agree, geo):
    if label == "can_empty": return min(CAP["can_empty"], CAP["unknown"])   # never above the crush-safe can cap, geometry or not
    if label == "stress_ball":
        try:
            from ai.object_profile import cap_for_votes
            return float(cap_for_votes("stress_ball", conf, agree))
        except Exception: return CAP["stress_ball"]
    return CAP.get(label, CAP["unknown"])


def perceive(head_rgb, head_depth, pixel_to_pelvis, vlm=(), vlm_timeout=12.0, self_mask=None):
    """self_mask: HxW bool robot pixels (robot_mask(...)(depth)) excluded from the objects."""
    t0 = time.time(); rgb = np.asarray(head_rgb); depth = np.asarray(head_depth)
    if not (depth > 0).any() or float(np.median(depth[depth > 0])) < 10.0:
        return {"table_z": None, "objects": [], "error": "depth not in mm or empty", "t_s": 0.0}
    tz, comps, _ = segment(rgb, depth, pixel_to_pelvis, self_mask)
    if tz is None: return {"table_z": None, "objects": [], "error": "no table plane in the workspace", "t_s": round(time.time() - t0, 2)}
    from ai.locate import locate
    vlm_votes = [[] for _ in comps]
    if vlm and comps:
        from ai.recognize import collect
        import concurrent.futures as cf
        with cf.ThreadPoolExecutor(max_workers=len(comps)) as ex:
            futs = [ex.submit(collect, _crop_jpeg(rgb, c["bbox"]), list(vlm), None, vlm_timeout) for c in comps]
            for i, f in enumerate(futs):
                try: vlm_votes[i] = f.result(timeout=vlm_timeout + 5)
                except Exception as e: vlm_votes[i] = [{"name": "vlm", "object": "other", "confidence": None, "ok": False, "error": type(e).__name__}]
    objs = []
    for c, vv in zip(comps, vlm_votes):
        geo = geometry_vote(rgb, c); label, conf, agree, why = decide([geo] + vv, geo)
        size_label = label if label != "unknown" else "unknown"
        try:
            r = locate(rgb, depth, pixel_to_pelvis, label=size_label, mask=c["mask"], table_z=tz)
        except Exception as e: r = {"p_pelvis": None, "depth_ok": False, "why": f"locate raised {type(e).__name__}: {e}"}
        p = r.get("p_pelvis")
        if p is None: p = [c["xy_top"][0], c["xy_top"][1], tz + c["height"] / 2]
        objs.append({"label": label, "conf": conf, "agree": agree, "cap": cap_for(label, conf, agree, geo), "p_pelvis": [round(float(x), 4) for x in p],
                     "depth_ok": bool(r.get("depth_ok", False)), "height": round(c["height"], 4), "bbox": c["bbox"], "area": c["area"],
                     "why": why, "locate_why": r.get("why"), "votes": [{k: v.get(k) for k in ("name", "object", "confidence", "ok", "error", "why")} for v in [geo] + vv]})
    return {"table_z": round(tz, 4), "objects": objs, "t_s": round(time.time() - t0, 2)}


def assign(objects, sides=("right", "left")):
    """Nearest object (to the shoulder, xy) on each side; objects refused by locate (depth_ok False) only if nothing else is there."""
    out = {}
    for s in sides:
        cand = [o for o in objects if (o["p_pelvis"][1] < 0) == (s == "right")]
        cand.sort(key=lambda o: (not o["depth_ok"], np.hypot(o["p_pelvis"][0] - SHOULDER[s][0], o["p_pelvis"][1] - SHOULDER[s][1])))
        out[s] = cand[0] if cand else None
    return out


MATCH_M = 0.05


def perceive_with_ai(head_rgb, head_depth, pixel_to_pelvis, vlm=(), vlm_timeout=12.0, self_mask=None):
    """Tommaso's ai.perceive (PR #149: VLM ensemble on crops + colour veto + locate gates) as the PRIMARY engine, run on the depth with the
    robot's own pixels set invalid (0), plus this module's geometry vote as one more recogniser (ai.perceive has no height rule, so without
    a working VLM a can is always 'unknown'). Objects are matched by xy (< 5 cm); label = fragile-first decide() over [geometry, ai.perceive];
    position = ai.perceive's when usable, else this module's; caps = V1 caps (CAP), ai.perceive's own cap is logged as ai_cap."""
    t0 = time.time(); rgb = np.asarray(head_rgb); depth = np.asarray(head_depth)
    mine = perceive(rgb, depth, pixel_to_pelvis, vlm=(), self_mask=self_mask)
    if mine.get("table_z") is None: return mine
    dm = depth.copy()
    if self_mask is not None: dm[np.asarray(self_mask, bool)] = 0
    info = {}
    try:
        from ai.perceive import perceive as ai_perceive, _default_recognizer
        ai_objs = ai_perceive(rgb, dm, pixel_to_pelvis, table_z=mine["table_z"],
                              recognizer=_default_recognizer(backends=tuple(vlm) + ("color",), timeout=vlm_timeout), timeout=vlm_timeout, debug=info)
    except Exception as e:
        mine["ai_error"] = f"{type(e).__name__}: {e}"; mine["engine"] = "g1 (ai.perceive failed)"; return mine
    ai_objs = [o for o in ai_objs if o.get("p_pelvis") is not None]; used = set(); out = []
    for o in mine["objects"]:
        geo = o["votes"][0]
        near = [(np.hypot(*(np.array(a["p_pelvis"][:2]) - o["p_pelvis"][:2])), i) for i, a in enumerate(ai_objs) if i not in used]
        near = [x for x in near if x[0] < MATCH_M]
        a = ai_objs[min(near)[1]] if near else None
        votes = [geo]
        if a is not None:
            used.add(ai_objs.index(a))
            votes.append({"name": "ai.perceive", "object": a["label"], "confidence": a.get("conf"), "ok": a["label"] != "unknown",
                          "why": a.get("why", "")[:200], "sub_votes": a.get("votes")})
        label, conf, agree, why = decide(votes, geo)
        p = a["p_pelvis"] if a is not None and a.get("usable") else o["p_pelvis"]
        ok = o["depth_ok"] and (a is None or a.get("depth_ok", True))
        out.append(dict(o, label=label, conf=conf, agree=agree, cap=cap_for(label, conf, agree, geo), p_pelvis=[round(float(x), 4) for x in p],
                        depth_ok=bool(ok), why=why, votes=votes, ai_cap=None if a is None else a.get("cap"), ai_label=None if a is None else a["label"]))
    for i, a in enumerate(ai_objs):          # seen only by ai.perceive (e.g. a flat object under 12 mm in this module's mask)
        if i in used: continue
        lab = a["label"]; out.append({"label": lab, "conf": a.get("conf"), "agree": a.get("agree", 0), "cap": CAP.get(lab, CAP["unknown"]),
                                      "p_pelvis": a["p_pelvis"], "depth_ok": bool(a.get("usable")), "height": None, "bbox": a.get("bbox"), "why": "ai.perceive only: " + a.get("why", "")[:200],
                                      "votes": [{"name": "ai.perceive", "object": lab, "confidence": a.get("conf"), "ok": lab != "unknown"}], "ai_cap": a.get("cap"), "ai_label": lab})
    return {"table_z": mine["table_z"], "objects": out, "t_s": round(time.time() - t0, 2), "engine": "ai.perceive+geometry", "ai_info": {k: info.get(k) for k in ("n_blobs", "proj_residual_m")}}
