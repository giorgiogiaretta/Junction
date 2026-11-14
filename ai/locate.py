"""Object POSITION from the G1 head RGB-D camera (Giorgio's contract, board 2026-11-14 12:39). Local, numpy only, no model call (< 100 ms).

  locate(head_rgb, head_depth, pixel_to_pelvis, label=None, conf=None, bbox=None)
  -> {"object", "conf", "p_pelvis": [x,y,z] m (object CENTRE), "axis_pelvis": [x,y,z] unit long axis or None, "bbox": [u0,v0,u1,v1],
      "depth_ok": bool (False = do not grasp: mixed depth, off-table surface or truncated), "truncated": bool, "occluded": bool, "p_surface": [x,y,z], "n_depth": int, "why": str}

Inputs: head_rgb HxWx3 uint8 RGB, head_depth HxW uint16 mm (0 = invalid), both 480x640 on the G1 (fx=fy=615, cx=320, cy=240).
pixel_to_pelvis(u, v, depth_mm) -> [x,y,z] metres in the pelvis frame: pass Erkka's cal.pixel_to_pelvis bound to "head"
(aaltonomous/interface/calibration, PROVISIONAL extrinsic). Without it the camera-frame point is returned (frame='camera').
Method: bbox from the caller (VLM / cv detector) or from a colour mask (white egg, orange ball, else 'unknown'); median of the valid depth
inside the object mask restricted to the central 50 % of the bbox; that pixel+depth -> pelvis = visible SURFACE point; centre = surface +
object radius further along the optical ray (upright cans: r along the HORIZONTAL part of the ray from the side points); optional z snap to the table plane (table_z + half height). Long axis: PCA of the mask,
mapped to the pelvis frame at the object depth. Sizes are nominal (egg 43x57 mm lying, ball ~65 mm, NOCCO can 58x146 mm standing).
UNTESTED on real G1 frames; accuracy measured only on synthetic renders (tests/test_locate.py)."""
import numpy as np

FX = FY = 615.0; CX, CY = 320.0, 240.0
# radius used to go from the visible surface to the centre (m), half height above the table (m)
SIZE = {"egg": (0.0215, 0.0215), "stress_ball": (0.0325, 0.0325), "can": (0.029, 0.073), "can_empty": (0.029, 0.073), "unknown": (0.025, None)}
MIN_DEPTH_PX = 20
EDGE_PX = 2          # object pixels/bbox within this many px of the frame edge = truncated -> refused


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


ROUND = {"stress_ball"}      # spheres: the silhouette must be ~round and ~2r*fx/depth wide, else partly hidden
ROUND_MIN_FILL = 0.8         # sim bench: every whole ball >= 0.96, the occluded one 0.62


def _grow(box, g):
    """Bool box mask grown by g px on each side (rectangle in, rectangle out)."""
    vs, us = np.nonzero(box); out = np.zeros_like(box)
    if len(us): out[max(0, vs.min() - g):vs.max() + g + 1, max(0, us.min() - g):us.max() + g + 1] = True
    return out


UPRIGHT = {"can", "can_empty"}   # standing cylinders: the axis is r away HORIZONTALLY from a side point (not along the 3D ray)


def _upright_centre(sel, depth, to3d, r, table_z=None, n_max=400):
    """Giorgio's fix (board 13:06): the camera looks ~48 deg down, so r along the full ray moves only ~0.67 r horizontally (~1 cm short
    for a can). Back-project the object pixels, keep SIDE points (below the top cap by > 5 mm, above the table), step r along the
    horizontal part of each pixel's ray, take the median. The top cap is ignored: its points are < r from the axis."""
    vs, us = np.nonzero(sel)
    if len(us) > n_max:
        k = np.linspace(0, len(us) - 1, n_max).astype(int); vs, us = vs[k], us[k]
    dd = depth[vs, us].astype(float)
    P = np.array([to3d(float(u), float(v), d) for u, v, d in zip(us, vs, dd)], float)
    Q = np.array([to3d(float(u), float(v), d + 1000.0) for u, v, d in zip(us, vs, dd)], float)
    side = P[:, 2] < np.percentile(P[:, 2], 95) - 0.005
    if table_z is not None: side &= P[:, 2] > table_z + 0.005   # background table/mat pixels inside a loose bbox
    H = (Q - P)[side]; H[:, 2] = 0.0; nrm = np.linalg.norm(H, axis=1)
    good = nrm > 1e-9
    if good.sum() < MIN_DEPTH_PX: return None
    return np.median(P[side][good] + r * H[good] / nrm[good, None], axis=0)


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
    obj = label or None; blob = None
    if bbox is None:   # pick the biggest colour blob of plausible object size
        sizes = {k: int(v.sum()) for k, v in masks.items()}
        cands = [k for k in masks if MIN_DEPTH_PX <= sizes[k] <= MAX_BLOB_PX]
        if not cands:
            return {"object": obj or "unknown", "conf": conf, "p_pelvis": None, "axis_pelvis": None, "bbox": None, "depth_ok": False,
                    "why": f"no bbox/mask given and no object-sized white/orange blob (px: {sizes})"}
        best = max(cands, key=lambda k: sizes[k])
        obj = obj or best; bbox = _bbox(masks[best]); blob = masks[best]
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
    if obj in UPRIGHT and pixel_to_pelvis is not None:   # needs a z-up frame for "horizontal"
        c_side = _upright_centre(sel, depth, to3d, r, table_z)
        if c_side is None:   # no usable side points: horizontal step from the median point
            h = ray * np.array([1.0, 1.0, 0.0]); c_side = surf + r * h / max(np.linalg.norm(h), 1e-9)
        centre = c_side
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
    # Refusal gates (Giorgio, board 13:00; sim egg bbox outlier 10.7 cm = table/mat depth mixed into the median). They only flip
    # depth_ok to False, never move the estimate: callers must not grasp when depth_ok is False.
    why = f"median depth {d:.0f} mm over {n} px, IQR {spread:.0f} mm"
    ok = spread < max(30.0, 2.0 * r * 1000.0)   # depth spread wider than the object diameter = mixed with background
    if not ok: why += f" > object diameter {2000 * r:.0f} mm: mixed with background"
    # Object cut off by the frame edge (Giorgio, board 13:13): 5 of 6 bench errors > 1 cm, centroid pulled to the visible part.
    # Test the RAW object pixels: the bbox is trimmed to the 1-99th percentile, so m = mask & box can lose the edge columns
    # (Giorgio, board 13:23: can #19 had 17 mask px in the last 2 columns and still got truncated=False).
    hh, ww = depth.shape; e = EDGE_PX
    if mask is not None: raw = mask                      # detector mask: object pixels only
    elif blob is not None:                               # colour blob: only near the box (other white/orange areas are not this object)
        raw = blob & _grow(box, 10)
    else: raw = m
    truncated = bool(u0 < e or v0 < e or u1 >= ww - e or v1 >= hh - e
                     or raw[:e].any() or raw[-e:].any() or raw[:, :e].any() or raw[:, -e:].any())
    if truncated: ok = False; why += "; object touches the image edge (truncated): move the head or the object"
    # Partly hidden sphere (Giorgio, board 13:23: sim ball #10 was 83x48 px where a whole one is ~78 px round, behind the arm).
    occluded = False
    if obj in ROUND:
        ext = _bbox(raw, pad=0) if mask is not None or blob is not None else [u0, v0, u1, v1]
        if ext is not None:
            want = 2.0 * r * FX / ((d + 1000.0 * r) / 1000.0)   # apparent diameter at the centre's depth (slightly small = lenient)
            fill = min(ext[2] - ext[0] + 1, ext[3] - ext[1] + 1) / want
            if fill < ROUND_MIN_FILL:
                occluded = True; ok = False; why += f"; round object only {fill:.2f} of its expected {want:.0f} px wide: occluded"
    if ok and table_z is not None and half_h is not None and pixel_to_pelvis is not None:
        hgt = 2.0 * half_h; zs = float(surf[2]) - table_z   # visible surface height above the table
        if not (0.25 * hgt <= zs <= hgt + 0.03):            # on the table/mat (or floating): not the object's surface
            ok = False; why += f"; surface {1000 * zs:.0f} mm above table, object is {1000 * hgt:.0f} mm tall: not on the object"
    return dict(out, p_pelvis=centre.round(4).tolist(), p_surface=surf.round(4).tolist(), axis_pelvis=axis, depth_ok=bool(ok),
                frame="pelvis" if pixel_to_pelvis else "camera", z_snapped=snapped, truncated=truncated, occluded=occluded, why=why)
