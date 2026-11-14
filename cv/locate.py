"""Validated RGB-D adapter over ai.locate; no robot commands or implied calibration.

Boxes use half-open pixel xyxy, matching cv.detect; ai.locate uses inclusive ends.
RGB/depth must already be aligned. Pass a calibrated pixel_to_pelvis callback;
without one no pelvis coordinates are returned. No automatic model download:
provide bbox/mask or explicitly inject detector=PIL_image -> list[{label,score,bbox}].
"""
import math
import numpy as np

KNOWN = {"egg", "stress_ball", "can", "can_empty"}


def _failure(why, label="unknown", conf=0.0, bbox=None):
    return {"object": label, "conf": conf, "bbox": bbox, "p_pelvis": None,
            "p_surface": None, "axis_pelvis": None, "depth_ok": False,
            "frame": None, "why": why, "n_depth": 0}


def locate(head_rgb, head_depth, pixel_to_pelvis=None, *, label=None, conf=None,
           bbox=None, mask=None, detector=None, table_z=None, min_confidence=.25):
    """Return the board locate schema; invalid/missing evidence returns depth_ok=False.

    Optional detector is called only when neither bbox nor mask is supplied. It
    receives PIL RGB (not BGR); e.g. Detector(device='cpu').detect. The highest-score
    accepted detection is selected. Explicit label filters detections; can_empty
    must be supplied by the caller, never inferred from appearance of a can.
    Pose comes from ai.locate's nominal surface-to-centre model, not measured shape.
    min_confidence applies only to detector results; explicit evidence/confidence
    is supplied by the caller. Calibration checks are numeric, not physical.
    A mask is required to report an axis; a bbox's shape is not an object axis.
    """
    from ai.locate import locate as geometry, MIN_DEPTH_PX

    try:
        rgb, depth = np.asarray(head_rgb), np.asarray(head_depth)
        if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
            return _failure("RGB must be HxWx3 uint8")
        h, w = rgb.shape[:2]
        if h == 0 or w == 0 or depth.shape != (h, w) or depth.dtype != np.uint16:
            return _failure("aligned depth must be HxW uint16 millimetres")
        if not callable(pixel_to_pelvis):
            return _failure("calibrated pixel_to_pelvis callback required; no camera-frame fallback")
        if label is not None and label not in KNOWN:
            return _failure("unsupported or unknown object label")
        if not math.isfinite(float(min_confidence)) or not 0 <= min_confidence <= 1:
            return _failure("min_confidence must be finite in [0,1]")
        if conf is not None and (not math.isfinite(float(conf)) or not 0 <= conf <= 1):
            return _failure("confidence must be finite in [0,1]")
        if table_z is not None and not math.isfinite(float(table_z)):
            return _failure("table_z must be finite metres in the calibrated frame")
        source = "mask" if mask is not None else "bbox"
        if bbox is None and mask is None:
            if not callable(detector):
                return _failure("no bbox/mask or explicit detector; colour-only fallback disabled")
            from PIL import Image
            try:
                detections = detector(Image.fromarray(rgb))
                candidates = []
                for d in detections:
                    candidate = d.get("label")
                    # Appearance-only backends cannot establish whether a can is empty.
                    candidate = "can" if candidate == "can_empty" else candidate
                    score = float(d.get("score", float("nan")))
                    match = label is None or candidate == label or (label == "can_empty" and candidate == "can")
                    if candidate in KNOWN and match and math.isfinite(score) and min_confidence <= score <= 1:
                        candidates.append(dict(d, label=candidate))
                if not candidates:
                    return _failure("detector returned no accepted object")
                best = max(candidates, key=lambda d: float(d["score"]))
                label = label or best["label"]
                conf, bbox, source = float(best["score"]), best["bbox"], "detector_bbox"
            except Exception as exc:
                return _failure(f"detector failed: {type(exc).__name__}")
        if label is None:
            return _failure("bbox/mask requires a known label; classification is not inferred from depth")
        confidence = float(conf) if conf is not None else 0.0
        box_out, box_inclusive = None, None
        if bbox is not None:
            b = np.asarray(bbox, dtype=float)
            if b.shape != (4,) or not np.isfinite(b).all():
                return _failure("bbox must contain four finite xyxy pixels")
            x0, y0, x1, y1 = b
            if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
                return _failure("bbox must be ordered, nonempty and within image bounds")
            box_out = [int(np.floor(x0)), int(np.floor(y0)), int(np.ceil(x1)), int(np.ceil(y1))]
            box_inclusive = [box_out[0], box_out[1], box_out[2]-1, box_out[3]-1]
        checked_mask = None
        if mask is not None:
            checked_mask = np.asarray(mask)
            if checked_mask.shape != (h, w) or checked_mask.dtype != np.bool_:
                return _failure("mask must be aligned HxW boolean")
            checked_mask = checked_mask.copy()
            if box_out is not None:
                support = np.zeros((h, w), bool)
                support[box_out[1]:box_out[3], box_out[0]:box_out[2]] = True
                checked_mask &= support
            if np.count_nonzero(checked_mask & (depth > 0)) < MIN_DEPTH_PX:
                return _failure("mask has too few valid depth pixels", label, confidence, box_out)

        def calibrated(u, v, dmm):
            p = np.asarray(pixel_to_pelvis(u, v, dmm), dtype=float)
            if p.shape != (3,) or not np.isfinite(p).all():
                raise ValueError("invalid calibration output")
            return p

        # Catch constant/broken transforms before the geometry normalizes its ray.
        check_box = box_out
        if check_box is None:
            ys, xs = np.nonzero(checked_mask)
            check_box = [int(xs.min()), int(ys.min()), int(xs.max())+1, int(ys.max())+1]
        u, v = (check_box[0]+check_box[2]-1)/2, (check_box[1]+check_box[3]-1)/2
        if np.linalg.norm(calibrated(u, v, 1500)-calibrated(u, v, 500)) < 1e-9:
            return _failure("calibration has a degenerate depth ray", label, confidence, box_out)
        with np.errstate(invalid="raise", divide="raise"):
            out = geometry(rgb, depth, calibrated, label=label, conf=confidence,
                           bbox=box_inclusive, mask=checked_mask, table_z=table_z)
        if not out.get("depth_ok"):
            return _failure(out.get("why", "geometry rejected depth"), label, confidence, box_out)
        for field in ("p_pelvis", "p_surface"):
            p = np.asarray(out.get(field), dtype=float)
            if p.shape != (3,) or not np.isfinite(p).all():
                return _failure("geometry returned invalid coordinates", label, confidence, box_out)
        if out.get("axis_pelvis") is not None and not np.isfinite(out["axis_pelvis"]).all():
            return _failure("geometry returned invalid axis", label, confidence, box_out)
        if box_out is None:
            b = out["bbox"]
            box_out = [b[0], b[1], b[2]+1, b[3]+1]
        out.update(bbox=box_out, evidence=source, frame="pelvis",
                   axis_pelvis=out.get("axis_pelvis") if checked_mask is not None else None)
        return out
    except Exception as exc:
        return _failure(f"invalid input/calibration or geometry failure: {type(exc).__name__}")
