"""Pre-grasp CROP: project the operating hand into the head-camera image and cut a window around it, so only that crop goes to the
vision-language model (fewer tokens, the model looks at the hand + the object it approaches).

Input geometry: `hand_in_head` = hand position [x, y, z] in metres expressed in the HEAD sensor frame (relative = inverse(head pose) * hand pose,
produced by Rokoko/ml). The camera is assumed rigidly attached to the head sensor. Default axes: head frame x right, y down, z forward
(OpenCV camera convention); use `axes` to remap, e.g. "x,-y,z" if the head sensor has y up. An optional `offset` = head-sensor origin expressed in
the camera frame (metres) accounts for the camera not sitting exactly on the sensor.

ASSUMED (replace with real calibration): the default intrinsics below (a GoPro-like 1920x1080 linear view, ~90 deg horizontal FOV), zero
camera-from-head offset and no lens distortion model. A wrong calibration only shifts the crop: it never sends data anywhere by itself.

Any missing/invalid input, a point behind the camera or outside the image -> the FULL image is returned and `reason` says why (cropped=False)."""
import io, json, math
from PIL import Image, ImageDraw

ASSUMED_INTRINSICS = {"fx": 960.0, "fy": 960.0, "cx": 960.0, "cy": 540.0, "width": 1920, "height": 1080, "assumed": True}
MIN_DEPTH_M = 0.05
_AXES = {"x": (0, 1), "y": (1, 1), "z": (2, 1), "-x": (0, -1), "-y": (1, -1), "-z": (2, -1)}


def load_intrinsics(path=None):
    """Intrinsics dict {fx,fy,cx,cy,width,height,assumed}. path=None -> ASSUMED defaults. A file missing keys falls back per key and keeps assumed=True."""
    if not path: return dict(ASSUMED_INTRINSICS)
    with open(path) as f: d = json.load(f)
    out, complete = dict(ASSUMED_INTRINSICS), True
    for k in ("fx", "fy", "cx", "cy", "width", "height"):
        if isinstance(d.get(k), (int, float)) and d[k] > 0: out[k] = float(d[k])
        else: complete = False
    out["assumed"] = not complete
    return out


def remap(p, axes="x,y,z"):
    """Remap a head-frame point to the camera frame (OpenCV: x right, y down, z forward). `axes` = 3 comma-separated tokens from x,y,z,-x,-y,-z."""
    toks = [t.strip().lower() for t in axes.split(",")]
    if len(toks) != 3 or any(t not in _AXES for t in toks): raise ValueError(f"bad axes {axes!r}")
    return [_AXES[t][1] * p[_AXES[t][0]] for t in toks]


def project(point_cam, K):
    """Pinhole projection -> (u, v, depth). Raises ValueError if depth <= MIN_DEPTH_M (point at/behind the camera)."""
    x, y, z = point_cam
    if not z > MIN_DEPTH_M: raise ValueError("behind camera")
    return K["fx"] * x / z + K["cx"], K["fy"] * y / z + K["cy"], z


def _jpeg(img, quality=90):
    b = io.BytesIO(); img.convert("RGB").save(b, "JPEG", quality=quality); return b.getvalue()


def crop_around_hand(image_bytes, hand_in_head, intrinsics=None, window_m=0.30, axes="x,y,z", offset=None, min_px=64):
    """-> {'image': jpeg bytes, 'bbox': [x0,y0,x1,y1] in image pixels, 'cropped': bool, 'reason': str, 'pixel': [u,v]|None, 'depth_m': float|None,
            'intrinsics_assumed': bool}. window_m = physical side of the square window at the hand's depth."""
    K = intrinsics or dict(ASSUMED_INTRINSICS)
    try: img = Image.open(io.BytesIO(image_bytes)); img.load()
    except Exception as e: return {"image": image_bytes, "bbox": None, "cropped": False, "reason": f"image decode failed: {e}", "pixel": None, "depth_m": None, "intrinsics_assumed": bool(K.get("assumed"))}
    W, H = img.size; full = [0, 0, W, H]
    def fallback(reason, pixel=None, depth=None):
        return {"image": _jpeg(img), "bbox": full, "cropped": False, "reason": reason, "pixel": pixel, "depth_m": depth, "intrinsics_assumed": bool(K.get("assumed"))}
    try:
        p = [float(v) for v in hand_in_head]
        if len(p) != 3 or any(not math.isfinite(v) for v in p): raise ValueError
    except (TypeError, ValueError): return fallback("no valid hand position")
    pc = remap(p, axes)
    if offset is not None: pc = [a + float(b) for a, b in zip(pc, offset)]
    sx, sy = W / K["width"], H / K["height"]                     # intrinsics may refer to another resolution
    Ks = dict(K, fx=K["fx"] * sx, fy=K["fy"] * sy, cx=K["cx"] * sx, cy=K["cy"] * sy)
    try: u, v, z = project(pc, Ks)
    except ValueError: return fallback("hand behind the camera", depth=pc[2])
    if not (0 <= u < W and 0 <= v < H): return fallback("hand outside the image", [u, v], z)
    side = max(float(min_px), window_m * Ks["fx"] / z)
    side = min(side, float(min(W, H)))                           # never larger than the image: keeps the box square
    x0 = min(max(u - side / 2, 0), W - side); y0 = min(max(v - side / 2, 0), H - side)   # shift inside the image instead of shrinking
    bbox = [int(round(x0)), int(round(y0)), int(round(x0 + side)), int(round(y0 + side))]
    if bbox[2] - bbox[0] >= W and bbox[3] - bbox[1] >= H: return fallback("crop covers the whole image", [u, v], z)
    return {"image": _jpeg(img.crop(tuple(bbox))), "bbox": bbox, "cropped": True, "reason": "ok", "pixel": [u, v], "depth_m": z, "intrinsics_assumed": bool(K.get("assumed"))}


def annotate(image_bytes, bbox, pixel=None):
    """Visual check: the image with the bbox (red) and the projected hand pixel (green cross) drawn. Returns JPEG bytes."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB"); d = ImageDraw.Draw(img)
    if bbox: d.rectangle(bbox, outline=(255, 0, 0), width=max(2, img.size[0] // 300))
    if pixel: u, v = pixel; r = max(6, img.size[0] // 120); d.line([(u - r, v), (u + r, v)], fill=(0, 255, 0), width=2); d.line([(u, v - r), (u, v + r)], fill=(0, 255, 0), width=2)
    return _jpeg(img)
