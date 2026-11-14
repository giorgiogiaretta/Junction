"""Object POSITION from the G1 head RGB-D camera (Giorgio's contract, board 2026-11-14 12:39). Local, numpy only, no model call (< 100 ms).

  locate(head_rgb, head_depth, pixel_to_pelvis, label=None, conf=None, bbox=None)
  -> {"object", "conf", "p_pelvis": [x,y,z] m (object CENTRE), "axis_pelvis": [x,y,z] unit long axis or None, "bbox": [u0,v0,u1,v1],
      "depth_ok": bool, "p_surface": [x,y,z], "n_depth": int, "why": str}

Inputs: head_rgb HxWx3 uint8 RGB, head_depth HxW uint16 mm (0 = invalid), both 480x640 on the G1 (fx=fy=615, cx=320, cy=240).
pixel_to_pelvis(u, v, depth_mm) -> [x,y,z] metres in the pelvis frame: pass Erkka's cal.pixel_to_pelvis bound to "head"
(aaltonomous/interface/calibration, PROVISIONAL extrinsic). Without it the camera-frame point is returned (frame='camera').
Method: bbox from the caller (VLM / cv detector) or from a colour mask (white egg, orange ball, else 'unknown'); median of the valid depth
inside the object mask restricted to the central 50 % of the bbox; that pixel+depth -> pelvis = visible SURFACE point; centre = surface +
object radius further along the optical ray; optional z snap to the table plane (table_z + half height). Long axis: PCA of the mask,
mapped to the pelvis frame at the object depth. Sizes are nominal (egg 43x57 mm lying, ball ~65 mm, NOCCO can 58x146 mm standing).
UNTESTED on real G1 frames; accuracy measured only on synthetic renders (tests/test_locate.py)."""
import numpy as np

FX = FY = 615.0; CX, CY = 320.0, 240.0
# radius used to go from the visible surface to the centre (m), half height above the table (m)
SIZE = {"egg": (0.0215, 0.0215), "stress_ball": (0.0325, 0.0325), "can": (0.029, 0.073), "can_empty": (0.029, 0.073), "unknown": (0.025, None)}
MIN_DEPTH_PX = 20


def camera_point(u, v, d_mm, fx=FX, fy=FY, cx=CX, cy=CY):
    """Pinhole back-projection in the optical frame (x right, y down, z forward), metres."""
    z = d_mm / 1000.0
    return [(u - cx) * z / fx, (v - cy) * z / fy, z]


def colour_mask(rgb):
    """{'egg': mask, 'stress_ball': mask}: white = bright and unsaturated; orange = R high, B low, G in between."""
    c = rgb.astype(np.int16); r, g, b = c[..., 0], c[..., 1], c[..., 2]
    mx, mn = c.max(-1), c.min(-1)
    white = (mn > 165) & (mx - mn < 45)
    orange = (r > 150) & (b < 110) & (r - b > 90) & (g > 50) & (g < r - 30)
    return {"egg": white, "stress_ball": orange}


MAX_BLOB_PX = 20000   # a 65 mm ball at >= 0.35 m from the camera covers < ~10000 px at fx 615; bigger white/orange areas = mats, walls, paper


def _bbox(mask, pad=2):
    vs, us = np.nonzero(mask)
    if len(us) < MIN_DEPTH_PX: return None
    u0, u1 = np.percentile(us, [1, 99]); v0, v1 = np.percentile(vs, [1, 99])   # robust to stray pixels
    h, w = mask.shape
    return [int(max(0, u0 - pad)), int(max(0, v0 - pad)), int(min(w - 1, u1 + pad)), int(min(h - 1, v1 + pad))]


def _axis_px(mask):
    vs, us = np.nonzero(mask)
    if len(us) < MIN_DEPTH_PX: return None, 1.0
    X = np.stack([us, vs], 1).astype(float); X -= X.mean(0)
    w, V = np.linalg.eigh(np.cov(X.T))
    return V[:, 1], float(np.sqrt(w[1] / max(w[0], 1e-9)))   # main direction (du, dv), elongation ratio


def locate(head_rgb, head_depth, pixel_to_pelvis=None, label=None, conf=None, bbox=None, table_z=None, elongated_min=1.1, mask=None):
    """mask: optional HxW bool object mask from a detector/segmenter (best); else bbox; else colour blobs (fallback, lighting-sensitive)."""
    rgb = np.asarray(head_rgb); depth = np.asarray(head_depth)
    masks = colour_mask(rgb)
    if mask is not None:
        mask = np.asarray(mask, bool); masks = {k: (mask if k == (label or "unknown") else v) for k, v in masks.items()}
        masks.setdefault(label or "unknown", mask)
        if bbox is None: bbox = _bbox(mask)
        if bbox is None:
            return {"object": label or "unknown", "conf": conf, "p_pelvis": None, "axis_pelvis": None, "bbox": None, "depth_ok": False,
                    "why": "given mask is (almost) empty"}
    obj = label or None
    if bbox is None:   # pick the biggest colour blob of plausible object size
        sizes = {k: int(v.sum()) for k, v in masks.items()}
        cands = [k for k in masks if MIN_DEPTH_PX <= sizes[k] <= MAX_BLOB_PX]
        if not cands:
            return {"object": obj or "unknown", "conf": conf, "p_pelvis": None, "axis_pelvis": None, "bbox": None, "depth_ok": False,
                    "why": f"no bbox/mask given and no object-sized white/orange blob (px: {sizes})"}
        best = max(cands, key=lambda k: sizes[k])
        obj = obj or best; bbox = _bbox(masks[best])
    u0, v0, u1, v1 = [int(x) for x in bbox]
    obj = obj or "unknown"
    box = np.zeros(depth.shape, bool); box[v0:v1 + 1, u0:u1 + 1] = True
    m = masks.get(obj, np.zeros_like(box)) & box
    if m.sum() < MIN_DEPTH_PX: m = box   # no colour support (e.g. can): use the whole bbox
    # central 50 % of the bbox
    du, dv = (u1 - u0) / 4.0, (v1 - v0) / 4.0
    core = np.zeros_like(box); core[int(v0 + dv):int(v1 - dv) + 1, int(u0 + du):int(u1 - du) + 1] = True
    sel = m & core & (depth > 0)
    if sel.sum() < MIN_DEPTH_PX: sel = m & (depth > 0)
    n = int(sel.sum())
    out = {"object": obj, "conf": conf, "bbox": [u0, v0, u1, v1], "n_depth": n}
    if n < MIN_DEPTH_PX:
        return dict(out, p_pelvis=None, axis_pelvis=None, depth_ok=False, why=f"only {n} valid depth pixels in the object")
    vs, us = np.nonzero(sel)
    d = float(np.median(depth[sel])); u, v = float(np.median(us)), float(np.median(vs))
    spread = float(np.percentile(depth[sel], 75) - np.percentile(depth[sel], 25))
    to3d = pixel_to_pelvis or (lambda uu, vv, dd: camera_point(uu, vv, dd))
    r, half_h = SIZE.get(obj, SIZE["unknown"])
    surf = np.asarray(to3d(u, v, d), float)
    ray = np.asarray(to3d(u, v, d + 1000.0), float) - surf   # depth is z-depth: points of one pixel are collinear, so this is the ray
    centre = surf + r * ray / np.linalg.norm(ray)
    snapped = False
    if table_z is not None and half_h is not None and pixel_to_pelvis is not None:
        centre[2] = table_z + half_h; snapped = True
    axis = None
    a, ratio = _axis_px(m)
    if a is not None and ratio >= elongated_min:
        L = 20.0
        p1 = np.asarray(to3d(u - a[0] * L, v - a[1] * L, d), float); p2 = np.asarray(to3d(u + a[0] * L, v + a[1] * L, d), float)
        ax = p2 - p1; nrm = np.linalg.norm(ax)
        if nrm > 0: axis = (ax / nrm).round(4).tolist()
    ok = spread < max(30.0, 2.5 * r * 1000.0)   # a depth spread wider than the object = mixed with background
    return dict(out, p_pelvis=centre.round(4).tolist(), p_surface=surf.round(4).tolist(), axis_pelvis=axis, depth_ok=bool(ok),
                frame="pelvis" if pixel_to_pelvis else "camera", z_snapped=snapped,
                why=f"median depth {d:.0f} mm over {n} px, IQR {spread:.0f} mm")
