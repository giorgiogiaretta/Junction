"""ALL objects on the table from ONE G1 head RGB-D frame (Giorgio's V1 request, board 2026-11-14 16:56). Call once at the first valid frame.

  from ai.perceive import perceive
  objs = perceive(head_rgb, head_depth, pixel_to_pelvis, table_z=None, recognizer=None, timeout=12.0)
  -> list of {"label": egg|can_empty|stress_ball|unknown, "conf": float|None, "agree": int, "cap": closure cap (ai.object_profile.cap_for_votes),
              "p_pelvis": [x,y,z] m (object centre), "axis": unit long axis|None, "usable": bool, "depth_ok": bool, "why": str,
              "source": "depth+vlm"|"depth+colour"|"depth", "bbox": [u0,v0,u1,v1], "votes": [...]}
  sorted usable first, then by distance from the robot. Use ONLY entries with usable=True (known label AND locate accepted the depth).

Method: (1) pixel_to_pelvis is a pinhole camera + rigid extrinsic, so p = A @ [u*d, v*d, d, 1] exactly; A (3x4) is fitted from 12 calls and
checked on 6 more (falls back to per-pixel calls if the residual is > 2 mm). (2) every pixel -> pelvis z; table_z = the most common height in
the lower 60 % of the image (or the given value). (3) pixels 12 mm .. 25 cm above the table, 4-connected blobs on a 4x downsampled grid,
footprint 2..20 cm (bigger = arm/robot/clutter, skipped). (4) each blob: crop -> ai.recognize ensemble (VLMs in parallel + colour rule,
fragile-first), all crops in parallel with one timeout; colour inside the blob cross-checks (white -> egg veto). (5) ai.locate with the
blob mask, the label and table_z: centre, axis and the refusal gates (mixed depth, truncated, occluded, off-table).
Depth: uint16 millimetres (0 = invalid), as G1 head_depth in sim and RealSense z16 at the default 0.001 scale; float input with
median < 10 is taken as metres and converted. 'can' from the recognisers is reported as can_empty (only empty cans in the demo; assumption).
UNTESTED on real G1 frames: synthetic renders only (tests/test_perceive.py)."""
import concurrent.futures as cf
import numpy as np
from ai.locate import locate, colour_mask

S = 4                    # downsampling for segmentation
MIN_H, MAX_H = 0.012, 0.25
MIN_PX = 6               # downsampled pixels per blob (~100 full-res)
MIN_EXT, MAX_EXT = 0.02, 0.20
LABEL = {"egg": "egg", "stress_ball": "stress_ball", "can": "can_empty"}


def fit_projection(to3d, w=640, h=480):
    """A (3x4) with pixel_to_pelvis(u,v,d) == A @ [u*d, v*d, d, 1] (d in mm). Returns (A, max residual m)."""
    rng = np.random.default_rng(0)
    def samples(n):
        return np.stack([rng.uniform(0, w, n), rng.uniform(0, h, n), rng.uniform(300, 1500, n)], 1)
    def design(X): return np.stack([X[:, 0] * X[:, 2], X[:, 1] * X[:, 2], X[:, 2], np.ones(len(X))], 1)
    X = samples(12); P = np.array([to3d(*x) for x in X], float)
    A = np.linalg.lstsq(design(X), P, rcond=None)[0].T
    Y = samples(6); Q = np.array([to3d(*y) for y in Y], float)
    return A, float(np.abs(design(Y) @ A.T - Q).max())


def _components(mask):
    lab = np.zeros(mask.shape, np.int32); n = 0; H, W = mask.shape
    for v0, u0 in zip(*np.nonzero(mask)):
        if lab[v0, u0]: continue
        n += 1; lab[v0, u0] = n; st = [(v0, u0)]
        while st:
            v, u = st.pop()
            for a, b in ((v + 1, u), (v - 1, u), (v, u + 1), (v, u - 1)):
                if 0 <= a < H and 0 <= b < W and mask[a, b] and not lab[a, b]: lab[a, b] = n; st.append((a, b))
    return lab, n


def _default_recognizer(backends=("nemotron", "gemma", "color"), timeout=12.0):
    def run(crop):
        import io
        from PIL import Image
        from ai.recognize import recognise
        b = io.BytesIO(); Image.fromarray(np.ascontiguousarray(crop)).save(b, "JPEG", quality=90)
        return recognise(b.getvalue(), backends, timeout=timeout)
    return run


def _colour_label(rgb, m):
    cm = colour_mask(rgb); n = max(int(m.sum()), 1)
    w, o = float((cm["egg"] & m).sum()) / n, float((cm["stress_ball"] & m).sum()) / n
    return ("egg", w) if w >= 0.5 else ("stress_ball", o) if o >= 0.5 else (None, max(w, o))


def perceive(head_rgb, head_depth, pixel_to_pelvis, table_z=None, recognizer=None, timeout=12.0, debug=None):
    from ai.object_profile import cap_for_votes
    rgb = np.asarray(head_rgb); depth = np.asarray(head_depth)
    if depth.dtype.kind == "f":
        depth = np.nan_to_num(depth, nan=0.0)
        if (depth > 0).any() and float(np.median(depth[depth > 0])) < 10.0: depth = depth * 1000.0   # metres -> mm
        depth = np.clip(np.round(depth), 0, 65535).astype(np.uint16)
    H, W = depth.shape; info = debug if debug is not None else {}
    A, res = fit_projection(pixel_to_pelvis, W, H); info["proj_residual_m"] = res
    if res <= 0.002: to3d = lambda u, v, d: (A @ np.array([u * d, v * d, d, 1.0])).tolist()
    else: to3d = pixel_to_pelvis
    dd = depth[S // 2::S, S // 2::S].astype(float); vv, uu = np.mgrid[S // 2:H:S, S // 2:W:S]; ok = dd > 0
    if res <= 0.002:
        z = (A[2, 0] * uu * dd + A[2, 1] * vv * dd + A[2, 2] * dd + A[2, 3])
        xy = np.stack([A[i, 0] * uu * dd + A[i, 1] * vv * dd + A[i, 2] * dd + A[i, 3] for i in (0, 1)], -1)
    else:
        P = np.full(dd.shape + (3,), np.nan)
        for a, b in zip(*np.nonzero(ok)): P[a, b] = pixel_to_pelvis(float(uu[a, b]), float(vv[a, b]), float(dd[a, b]))
        z, xy = P[..., 2], P[..., :2]
    if table_z is None:
        low = ok.copy(); low[: int(0.4 * low.shape[0])] = False
        zs = z[low] if low.any() else z[ok]
        if not len(zs): info["error"] = "no valid depth"; return []
        hist, edges = np.histogram(zs, bins=np.arange(zs.min(), zs.max() + 0.01, 0.005))
        k = int(np.argmax(hist)); table_z = float(zs[(zs >= edges[k]) & (zs < edges[k + 1])].mean()); info["table_z_est"] = round(table_z, 4)
    above = ok & (z > table_z + MIN_H) & (z < table_z + MAX_H)
    lab, n = _components(above); blobs = []; info["skipped"] = []
    for i in range(1, n + 1):
        c = lab == i
        if c.sum() < MIN_PX: continue
        e = xy[c]; ext = float(np.max(e.max(0) - e.min(0)))
        if not (MIN_EXT <= ext <= MAX_EXT): info["skipped"].append({"px": int(c.sum()), "extent_m": round(ext, 3)}); continue
        full = np.kron(c, np.ones((S, S), bool))[:H, :W]
        full = np.pad(full, ((0, H - full.shape[0]), (0, W - full.shape[1])))
        dmax = float(dd[c].max()); full &= (depth > 0) & (depth <= dmax + 15)
        vs, us = np.nonzero(full)
        if len(us) < 20: continue
        u0, u1, v0, v1 = int(us.min()), int(us.max()), int(vs.min()), int(vs.max()); pu, pv = (u1 - u0) // 4 + 8, (v1 - v0) // 4 + 8
        crop = rgb[max(0, v0 - pv):min(H, v1 + pv + 1), max(0, u0 - pu):min(W, u1 + pu + 1)]
        blobs.append({"mask": full, "bbox": [u0, v0, u1, v1], "crop": crop})
    info["n_blobs"] = len(blobs)
    rec = recognizer or _default_recognizer(timeout=timeout)
    ex = cf.ThreadPoolExecutor(max_workers=max(1, len(blobs)))
    futs = [ex.submit(rec, b["crop"]) for b in blobs]
    cf.wait(futs, timeout=timeout + 3.0); ex.shutdown(wait=False, cancel_futures=True)
    out = []
    for b, f in zip(blobs, futs):
        try: r = f.result(timeout=0) if f.done() else {"object": "other", "confidence": None, "agree": 0, "n_ok": 0, "reason": "timeout"}
        except Exception as e: r = {"object": "other", "confidence": None, "agree": 0, "n_ok": 0, "reason": type(e).__name__}
        label = LABEL.get(r.get("object"), "unknown"); conf = r.get("confidence"); agree = int(r.get("agree") or 0)
        source = "depth+vlm" if any(v.get("ok") and v.get("name") != "color" for v in r.get("votes", [])) else "depth"
        col, frac = _colour_label(rgb, b["mask"])
        why = r.get("reason", "")
        if col == "egg" and label != "egg":           # fragile-first: white blob = treat as egg whatever the models say
            label, why = "egg", f"colour veto: {frac:.0%} white pixels -> egg (models: {r.get('object')})"
        elif label == "unknown" and col is not None:   # no model answer: colour rule alone (no full force from it)
            label, conf, agree, source, why = col, None, 1, "depth+colour", f"no model answer, colour {frac:.0%} -> {col}"
        loc = locate(rgb, depth, to3d, label=label if label != "unknown" else None, conf=conf, mask=b["mask"], table_z=table_z)
        cap = cap_for_votes("can" if label == "can_empty" else label if label != "unknown" else "other", conf, agree)
        out.append({"label": label, "conf": conf, "agree": agree, "cap": cap, "p_pelvis": loc.get("p_pelvis"), "axis": loc.get("axis_pelvis"),
                    "depth_ok": bool(loc.get("depth_ok")), "usable": bool(loc.get("depth_ok")) and label != "unknown" and loc.get("p_pelvis") is not None,
                    "why": f"{why}; locate: {loc.get('why')}", "source": source, "bbox": b["bbox"],
                    "votes": [{k: v.get(k) for k in ("name", "object", "confidence", "ok")} for v in r.get("votes", [])]})
    out.sort(key=lambda o: (not o["usable"], np.linalg.norm(o["p_pelvis"][:2]) if o["p_pelvis"] else 9.0))
    return out
