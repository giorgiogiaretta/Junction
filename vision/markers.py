"""Detect the 4 yellow-green tape X markers at the corners of the table square and order them BL, TL, TR, BR.

Ordering convention (viewed from above, camera 'looking from the BL-BR edge'): BL is the bottom-left corner of the
quad in the image, then clockwise on screen: BL -> TL -> TR -> BR. If the camera sits elsewhere pass `rotate`
(0-3) to shift the labels by quarter turns, or use manual selection (`pick_manual`)."""
import itertools
import cv2
import numpy as np

# OpenCV HSV (H 0-179). Yellow-green tape; widened so it survives different lighting. Override via detect_markers(hsv_lo=, hsv_hi=).
HSV_LO = (19, 40, 110)
HSV_HI = (45, 255, 255)

def marker_mask(bgr, hsv_lo=HSV_LO, hsv_hi=HSV_HI):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, np.array(hsv_lo, np.uint8), np.array(hsv_hi, np.uint8))
    scale = max(bgr.shape[:2]) / 1000.0
    k = max(3, int(round(5 * scale)) | 1)
    # close tiny gaps along the tape strokes, then drop speckles
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return m

def _arms(b):
    """Number of angular lobes of a binary blob beyond 60% of its max radius from the centroid (X ~ 4)."""
    ys, xs = np.nonzero(b)
    if len(xs) < 10: return 0
    dx, dy = xs - xs.mean(), ys - ys.mean(); r = np.hypot(dx, dy)
    far = r > 0.6 * r.max()
    h = np.histogram(np.arctan2(dy[far], dx[far]), bins=36, range=(-np.pi, np.pi))[0] > 0
    # close single-bin gaps, then count circular runs
    h = h | (np.roll(h, 1) & np.roll(h, -1))
    return int(np.sum(h & ~np.roll(h, 1))) if not h.all() else 1

def find_candidates(bgr, hsv_lo=HSV_LO, hsv_hi=HSV_HI):
    """Return list of dicts (centroid xy, area, bbox, xness) for X-like blobs, best first."""
    m = marker_mask(bgr, hsv_lo, hsv_hi)
    n, lab, stats, cents = cv2.connectedComponentsWithStats(m, connectivity=8)
    H, W = m.shape
    min_area = 0.00004 * H * W
    out = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a < min_area or a > 0.02 * H * W: continue
        ar = max(w, h) / max(1, min(w, h))
        if ar > 3.5: continue                      # long strips are not an X seen from a reasonable angle
        b = (lab[y:y + h, x:x + w] == i).astype(np.uint8)
        cnt, _ = cv2.findContours(b, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        hull = cv2.contourArea(cv2.convexHull(max(cnt, key=cv2.contourArea)))
        solidity = a / max(1.0, hull)              # an X is sparse in its convex hull (~0.4-0.65); solid blobs/labels are not
        width = 2 * cv2.distanceTransform(np.pad(b, 1), cv2.DIST_L2, 3).max() / max(w, h)   # stroke width vs extent
        if solidity > 0.72 or width > 0.40: continue
        arms = _arms(b)
        if not 2 <= arms <= 6: continue            # an X has 4 arms around its crossing; deviations are penalised in the ranking
        fill = solidity
        # the true centre of an X is the centre of the strokes' crossing = blob centroid (symmetric shape)
        out.append(dict(xy=tuple(map(float, cents[i])), area=int(a), arms=arms, bbox=(int(x), int(y), int(w), int(h)),
                        score=float(a) * (1.0 - abs(fill - 0.3))))
    out.sort(key=lambda d: -d["score"])
    return out

def order_corners(pts, rotate=0):
    """pts: 4x2 image points -> array [BL, TL, TR, BR] (see module docstring)."""
    p = np.asarray(pts, float).reshape(4, 2)
    c = p.mean(0)
    ang = np.arctan2(p[:, 1] - c[1], p[:, 0] - c[0])       # image coords (y down): increasing angle = clockwise on screen
    p = p[np.argsort(ang)]                                   # clockwise
    bl = int(np.argmin(p[:, 0] - p[:, 1]))                   # most left & most bottom (y large)
    p = np.roll(p, -bl, axis=0)                              # BL, TL, TR, BR clockwise
    return np.roll(p, -(rotate % 4), axis=0)

def _quad_ok(q):
    """Convex, non-degenerate quad, sides within a loose perspective range."""
    q = order_corners(q)
    if cv2.contourArea(q.astype(np.float32)) < 100: return False
    if not cv2.isContourConvex(q.astype(np.float32).reshape(-1, 1, 2)): return False
    s = [np.linalg.norm(q[i] - q[(i + 1) % 4]) for i in range(4)]
    return max(s) / max(1e-6, min(s)) < 5.0

def squareness(pts, size):
    """How well 4 ordered image points (BL,TL,TR,BR) can be the perspective image of a SQUARE seen by a pinhole camera with
    its principal point at the image centre and unknown focal length: for the best focal length the images of the square's two
    axes must be orthogonal and of equal length in camera space. Returns 0 (perfect) .. ~1 (impossible). size=(w,h) of the image.
    This is what rejects yellow snack bags / green cans that merely look like blobs; no calibration needed."""
    q = order_corners(pts)
    sq = np.array([[-1, -1], [-1, 1], [1, 1], [1, -1]], np.float32)
    H = cv2.getPerspectiveTransform(sq, q.astype(np.float32))
    T = np.array([[1, 0, -size[0] / 2.0], [0, 1, -size[1] / 2.0], [0, 0, 1]])
    Hc = T @ H
    best = 9.0
    for f in np.geomspace(0.3, 6.0, 40) * max(size):
        Ki = np.diag([1 / f, 1 / f, 1.0])
        n1, n2 = Ki @ Hc[:, 0], Ki @ Hc[:, 1]
        l1, l2 = np.linalg.norm(n1), np.linalg.norm(n2)
        best = min(best, abs(n1 @ n2) / (l1 * l2) + abs(l1 - l2) / (l1 + l2))
    return float(best)

def detect_markers(bgr, rotate=0, hsv_lo=HSV_LO, hsv_hi=HSV_HI, roi=None, max_sq=0.2):
    """Return (pts[4,2] ordered BL,TL,TR,BR, info) or (None, info) when 4 markers are not found.
    info['n_candidates'], info['all'] (candidate centroids); with 3 visible markers info['n_found']==3 (not enough)."""
    img = bgr
    if roi is not None:
        x, y, w, h = roi; img = bgr[y:y + h, x:x + w]
    cands = find_candidates(img, hsv_lo, hsv_hi)[:12]
    off = np.array(roi[:2], float) if roi is not None else np.zeros(2)
    info = dict(n_candidates=len(cands), all=[tuple(np.add(c["xy"], off)) for c in cands])
    if len(cands) < 4: return None, info
    best, bs = None, 1e9
    for combo in itertools.combinations(range(len(cands)), 4):
        areas = np.array([cands[i]["area"] for i in combo], float)
        pts = np.array([cands[i]["xy"] for i in combo])
        if not _quad_ok(pts): continue
        sim = areas.min() / areas.max()            # same tape: perspective changes the areas only mildly
        if sim < 0.12: continue
        sq = squareness(pts, bgr.shape[1::-1])
        if sq > max_sq: continue
        s = sq + 0.1 * (1 - sim) + 0.05 * sum(abs(cands[i]["arms"] - 4) for i in combo)
        if s < bs: best, bs = pts, s
    info["squareness"] = None if best is None else bs
    if best is None: return None, info
    return order_corners(best + off, rotate), info

def calibrate_from_frames(frames, rotate=0, min_presence=0.15, tol_frac=0.02, hsv_lo=HSV_LO, hsv_hi=HSV_HI, max_sq=0.2, transforms=None):
    """FIXED camera: find the 4 markers that persist at the same pixels over many frames (false positives such as the can,
    snack bags or hands move or flicker, the tape does not). frames: iterable of BGR images.
    Returns (pts[4,2] ordered, info) with info['presence'] and info['spread_px'] (std of each marker centre across frames);
    (None, info) if fewer than 4 persistent X were found.
    transforms: optional 3x3 per frame (moving camera, see homography.CameraMotion) mapping each frame into a common reference."""
    obs = []; n = 0; diag = 1.0; size = (1, 1)
    for k, f in enumerate(frames):
        n += 1; diag = float(np.hypot(*f.shape[:2])); size = f.shape[1::-1]
        cc = find_candidates(f, hsv_lo, hsv_hi); xy = [c["xy"] for c in cc]; ar = [(c["area"], c["arms"]) for c in cc]
        if transforms is not None and xy:
            xy = cv2.perspectiveTransform(np.array(xy, float).reshape(-1, 1, 2), transforms[k]).reshape(-1, 2).tolist()
        obs += [(p[0], p[1], a[0], a[1]) for p, a in zip(xy, ar)]
    tol = tol_frac * diag
    clusters = []
    for p in obs:
        for c in clusters:
            if np.hypot(*(np.array(p[:2]) - np.mean(c, 0)[:2])) < tol: c.append(p); break
        else: clusters.append([p])
    clusters = [c for c in clusters if len(c) / max(1, n) >= min_presence]
    clusters.sort(key=lambda c: -len(c))
    info = dict(n_frames=n, n_clusters=len(clusters), presence=[len(c) / max(1, n) for c in clusters[:6]])
    if len(clusters) < 4: return None, info
    best = None
    for combo in itertools.combinations(range(min(len(clusters), 8)), 4):
        pts = np.array([np.median(clusters[i], 0)[:2] for i in combo]); areas = np.array([np.median(np.array(clusters[i])[:, 2]) for i in combo])
        if not _quad_ok(pts) or squareness(pts, size) > max_sq: continue
        s = np.mean([len(clusters[i]) for i in combo]) / n - 4.0 * squareness(pts, size) - 1.0 * (1 - areas.min() / areas.max()) - 0.15 * np.mean([abs(np.median(np.array(clusters[i])[:, 3]) - 4) for i in combo])
        if best is None or s > best[0]: best = (s, combo, pts)
    if best is None: return None, info
    info["spread_px"] = [float(np.std(np.array(clusters[i])[:, :2], 0).mean()) for i in best[1]]
    return order_corners(best[2], rotate), info

def pick_manual(bgr, window="click 4 corners: BL, TL, TR, BR (then Enter)"):
    """Fallback: click the 4 marker centres in order BL, TL, TR, BR. Returns 4x2 float array (None if aborted)."""
    pts = []
    vis = bgr.copy()
    def cb(ev, x, y, *_):
        if ev == cv2.EVENT_LBUTTONDOWN and len(pts) < 4:
            pts.append((x, y)); cv2.circle(vis, (x, y), 5, (0, 0, 255), -1)
    cv2.namedWindow(window); cv2.setMouseCallback(window, cb)
    while True:
        cv2.imshow(window, vis)
        k = cv2.waitKey(30) & 0xFF
        if k == 27: pts = None; break
        if k in (13, 10) and len(pts) == 4: break
    cv2.destroyWindow(window)
    return None if pts is None else np.array(pts, float)

if __name__ == "__main__":
    import argparse, json, sys
    ap = argparse.ArgumentParser(description="Detect table markers in an image/video frame; --manual to click them.")
    ap.add_argument("source"); ap.add_argument("--frame", type=int, default=0); ap.add_argument("--manual", action="store_true")
    ap.add_argument("--rotate", type=int, default=0); ap.add_argument("--out", help="save the 4 points to this json")
    a = ap.parse_args()
    img = cv2.imread(a.source)
    if img is None:
        c = cv2.VideoCapture(a.source); c.set(cv2.CAP_PROP_POS_FRAMES, a.frame); ok, img = c.read()
        if not ok: sys.exit("cannot read source")
    pts = pick_manual(img) if a.manual else detect_markers(img, a.rotate)[0]
    print("points BL,TL,TR,BR:", None if pts is None else pts.round(1).tolist())
    if pts is not None and a.out: json.dump(pts.tolist(), open(a.out, "w"))
