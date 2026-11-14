"""Can tracking in table coordinates (metres), FIXED camera.

Detection = foreground vs a background model of the empty table (temporal median over the clip: the can and the hands move,
the table does not), restricted to the table square plus a margin, optionally AND-ed with a can colour range (`can_hsv`)
for extra robustness (the wood and the orange can have similar hue, so colour alone is NOT a safe default). Dark pixels
(black gloves) are never can. The can is the compact blob whose area in cm^2 on the table is plausible, closest to the previous
position. Position = blob centroid intersected with the plane at ~60% of the can height when camera intrinsics are known
(else z=0). Quality flags: Q_OK measured, Q_PARTIAL small/occluded blob or position held, Q_LOST not seen for too long."""
import cv2
import numpy as np
from .homography import table_corners

Q_LOST, Q_PARTIAL, Q_OK = 0, 1, 2
CAN_D, CAN_H = 0.066, 0.115          # metres (standard short can, 66 x 115 mm)

def build_background(frames):
    """Per-pixel temporal median of BGR frames (list/iterable). Needs the can to be away from each pixel >50% of the time."""
    return np.median(np.stack(list(frames), 0), axis=0).astype(np.uint8)

def _px_area_to_cm2(calib, px, area_px):
    """Local scale of the pixel->table map at px (finite-difference Jacobian), applied to a pixel area."""
    e = 3.0
    a = calib.pixel_to_table(np.array([px, px + [e, 0], px + [0, e]], float))
    J = np.array([(a[1] - a[0]) / e, (a[2] - a[0]) / e]).T
    return abs(np.linalg.det(J)) * area_px * 1e4

class CanTracker:
    def __init__(self, calib, background=None, can_hsv=None, margin=0.10, thr=28, can_h=CAN_H,
                 area_cm2=(8.0, 160.0), hold_frames=15, use_height=True, anchor=0.6):
        if background is None and can_hsv is None: raise ValueError("need a background model or a can colour range")
        self.calib, self.bg, self.can_hsv, self.thr = calib, background, can_hsv, thr
        self.margin, self.can_h, self.area_cm2, self.hold = margin, can_h, area_cm2, hold_frames
        self.use_height, self.anchor = use_height, anchor   # anchor: fraction of can height where the silhouette centroid is
        # intersected; 0.6 not 0.5 because the nearer top face looks bigger, which pulls the silhouette centroid upwards (calibrated on synthetic renders)
        self.prev, self.miss, self.nominal = None, 10 ** 6, None
        self._roi_cache = None

    def roi_mask(self, shape):
        key = (shape[:2], self.calib.img_pts.tobytes())
        if self._roi_cache and self._roi_cache[0] == key: return self._roi_cache[1]
        c = table_corners(self.calib.side); h = self.calib.side / 2 + self.margin
        quad = np.array([[-h, -h], [-h, h], [h, h], [h, -h]])
        pix = self.calib.table_to_pixel(quad).astype(np.int32)
        m = np.zeros(shape[:2], np.uint8); cv2.fillConvexPoly(m, pix, 255)
        self._roi_cache = (key, m)
        return m

    def mask(self, bgr):
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        m = np.full(bgr.shape[:2], 255, np.uint8)
        if self.bg is not None:
            d = cv2.absdiff(cv2.GaussianBlur(bgr, (5, 5), 0), cv2.GaussianBlur(self.bg, (5, 5), 0)).max(axis=2)
            m &= (d > self.thr).astype(np.uint8) * 255
        if self.can_hsv is not None:
            lo, hi = self.can_hsv
            m &= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
        m &= (hsv[..., 2] > 60).astype(np.uint8) * 255            # black gloves are not the can
        m &= self.roi_mask(bgr.shape)
        k = max(3, int(max(bgr.shape[:2]) / 250) | 1)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
        return cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))

    def update(self, bgr):
        """Returns dict(xy=(x,y) metres or (nan,nan), q=Q_*, area_cm2, px=(u,v) or None)."""
        m = self.mask(bgr)
        n, lab, st, ce = cv2.connectedComponentsWithStats(m, connectivity=8)
        best, bs = None, None
        for i in range(1, n):
            area = _px_area_to_cm2(self.calib, ce[i], st[i, cv2.CC_STAT_AREA])
            if not (self.area_cm2[0] <= area <= self.area_cm2[1]): continue
            xy = self.calib.pixel_to_table(ce[i])
            cost = 0.0 if self.prev is None else float(np.hypot(*(xy - self.prev)))   # continuity (metres)
            cost += 0.002 * abs(area - (self.nominal or 40.0))                           # similar size as before
            if bs is None or cost < bs: best, bs = (i, area, xy), cost
        if best is not None:
            i, area, _ = best
            px = ce[i]
            z = self.anchor * self.can_h if (self.use_height and self.calib.R is not None) else 0.0
            xy = self.calib.pixel_to_table(px, z)
            partial = self.nominal is not None and area < 0.55 * self.nominal
            if not partial: self.nominal = area if self.nominal is None else 0.9 * self.nominal + 0.1 * area
            self.prev, self.miss = xy, 0
            return dict(xy=tuple(xy), q=Q_PARTIAL if partial else Q_OK, area_cm2=float(area), px=tuple(px))
        self.miss += 1
        if self.prev is not None and self.miss <= self.hold:      # occluded by the hand: hold the last position
            return dict(xy=tuple(self.prev), q=Q_PARTIAL, area_cm2=0.0, px=None)
        return dict(xy=(np.nan, np.nan), q=Q_LOST, area_cm2=0.0, px=None)
