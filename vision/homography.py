"""Pixel -> table-plane metres. Table frame: origin at the square's centre, x = BL->BR, y = BL->TL, z up (metres).
Corner order everywhere: BL, TL, TR, BR (see markers.py)."""
import json
import cv2
import numpy as np

SIDE = 0.297   # metres, side of the marker square (measured with a tape measure)

def table_corners(side=SIDE):
    h = side / 2.0
    return np.array([[-h, -h], [-h, h], [h, h], [h, -h]], float)   # BL, TL, TR, BR

def intrinsics_from_hfov(width, height, hfov_deg):
    """Pinhole K from horizontal field of view (no distortion). Only as good as the FOV you give it."""
    f = (width / 2.0) / np.tan(np.radians(hfov_deg) / 2.0)
    return np.array([[f, 0, width / 2.0], [0, f, height / 2.0], [0, 0, 1.0]])

class TableCalib:
    """Holds H (image px -> table metres) and, when intrinsics K are known, the camera pose so that points above the table
    (e.g. the middle of the can, ~5.7 cm up) are intersected with the plane z=const instead of being projected on z=0."""
    def __init__(self, img_pts, side=SIDE, K=None, dist=None):
        self.side = side
        self.K = None if K is None else np.asarray(K, float)
        self.dist = None if dist is None else np.asarray(dist, float).reshape(-1)
        self.set_points(img_pts)

    def _undist(self, pts):
        pts = np.asarray(pts, float).reshape(-1, 2)
        if self.K is None or self.dist is None or not np.any(self.dist): return pts
        return cv2.undistortPoints(pts.reshape(-1, 1, 2), self.K, self.dist, P=self.K).reshape(-1, 2)

    def set_points(self, img_pts):
        """(Re)fit from 4 marker centres (BL,TL,TR,BR). Also used for per-frame updates with a moving camera."""
        self.img_pts = np.asarray(img_pts, float).reshape(4, 2)
        u = self._undist(self.img_pts)
        self.H = cv2.getPerspectiveTransform(u.astype(np.float32), table_corners(self.side).astype(np.float32))
        self.R = self.t = None
        if self.K is not None:
            dist = self.dist if self.dist is not None else np.zeros(5)
            ok, rvec, tvec = cv2.solvePnP(np.c_[table_corners(self.side), np.zeros(4)], self.img_pts, self.K, dist,
                                           flags=cv2.SOLVEPNP_IPPE)
            if ok: self.R, _ = cv2.Rodrigues(rvec); self.t = tvec.reshape(3)
        return self

    def pixel_to_table(self, pts, z=0.0):
        """pts: (N,2) or (2,) pixels -> same shape in metres on the plane at height z (default: the table surface)."""
        a = np.asarray(pts, float); single = a.ndim == 1; p = a.reshape(-1, 2)
        if abs(z) < 1e-9 or self.R is None:
            out = cv2.perspectiveTransform(self._undist(p).reshape(-1, 1, 2), self.H).reshape(-1, 2)
        else:
            dist = self.dist if self.dist is not None else np.zeros(5)
            n = cv2.undistortPoints(p.reshape(-1, 1, 2), self.K, dist).reshape(-1, 2)    # normalised camera coords
            d = np.c_[n, np.ones(len(n))] @ self.R                                        # R^T d, row-vector form
            C = -self.R.T @ self.t                                                        # camera centre in table frame
            lam = (z - C[2]) / d[:, 2]
            out = (C[None, :] + lam[:, None] * d)[:, :2]
        return out[0] if single else out

    def table_to_pixel(self, xy, z=0.0):
        a = np.asarray(xy, float); single = a.ndim == 1; p = a.reshape(-1, 2)
        if self.K is not None and self.R is not None:
            rv, _ = cv2.Rodrigues(self.R)
            dist = self.dist if self.dist is not None else np.zeros(5)
            out = cv2.projectPoints(np.c_[p, np.full(len(p), z)], rv, self.t, self.K, dist)[0].reshape(-1, 2)
        else:
            out = cv2.perspectiveTransform(p.reshape(-1, 1, 2), np.linalg.inv(self.H)).reshape(-1, 2)
        return out[0] if single else out

    def corner_residual_mm(self):
        """Marker centres mapped through H vs the ideal square (mm). ~0 by construction with exactly 4 points; informative
        only together with `jitter_mm` (spread of per-frame fits)."""
        return float(np.abs(self.pixel_to_table(self.img_pts) - table_corners(self.side)).max() * 1000)

    def to_json(self):
        return dict(side=self.side, img_pts=self.img_pts.tolist(), K=None if self.K is None else self.K.tolist(),
                    dist=None if self.dist is None else self.dist.tolist())

    @classmethod
    def from_json(cls, d):
        return cls(d["img_pts"], d.get("side", SIDE), d.get("K"), d.get("dist"))

    def save(self, path): json.dump(self.to_json(), open(path, "w"), indent=1)

    @classmethod
    def load(cls, path): return cls.from_json(json.load(open(path)))

def jitter_mm(per_frame_pts, side=SIDE):
    """per_frame_pts: list of 4x2 marker fits from a FIXED camera. RMS distance (mm) of the per-frame marker centres from
    the ideal square, measured in the table frame of the median fit: a real measure of detection noise / camera bumps."""
    arr = np.array(per_frame_pts, float)
    cal = TableCalib(np.median(arr, axis=0), side)
    tab = np.array([cal.pixel_to_table(p) for p in arr])
    return float(np.sqrt(((tab - table_corners(side)[None]) ** 2).sum(-1).mean()) * 1000)

class CameraMotion:
    """Optional: follow a moving (hand-held / bumped) camera by matching ORB features to a reference frame.
    `to_ref(frame)` returns (M, ok): M maps pixels of `frame` into the reference frame's pixels."""
    def __init__(self, ref_bgr, mask=None):
        self.orb = cv2.ORB_create(2000)
        self.bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        self.kp, self.des = self.orb.detectAndCompute(cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY), mask)
        self.last = np.eye(3)

    def to_ref(self, bgr):
        kp, des = self.orb.detectAndCompute(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), None)
        if des is None or self.des is None: return self.last, False
        m = self.bf.match(des, self.des)
        if len(m) < 20: return self.last, False
        src = np.float32([kp[x.queryIdx].pt for x in m]); dst = np.float32([self.kp[x.trainIdx].pt for x in m])
        M, inl = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
        if M is None or inl.sum() < 20: return self.last, False
        self.last = M
        return M, True

def apply_h(M, pts):
    p = np.asarray(pts, float).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(p, M).reshape(-1, 2)
