"""Synthetic tests for vision/: 4 tape X + a can rendered with a known camera, everything must be recovered in table metres."""
import json, pathlib, sys
import cv2
import numpy as np
ROOT = pathlib.Path(__file__).parents[1]; sys.path.insert(0, str(ROOT))
from vision.markers import detect_markers, calibrate_from_frames, order_corners, squareness
from vision.homography import TableCalib, intrinsics_from_hfov, table_corners, SIDE
from vision.can_track import CanTracker, build_background, Q_OK, CAN_D, CAN_H

W, H = 1280, 720
K = intrinsics_from_hfov(W, H, 100.0)

def make_pose(cam=(0.12, -0.30, 0.80), target=(0, 0, 0)):
    C = np.array(cam, float); z = np.array(target, float) - C; z /= np.linalg.norm(z)
    x = np.cross(z, [0, 0, 1.0]); x /= np.linalg.norm(x); y = np.cross(z, x)
    R = np.stack([x, y, z]); t = -R @ C
    return cv2.Rodrigues(R)[0], t

def project(rvec, t, pts3):
    return cv2.projectPoints(np.asarray(pts3, float).reshape(-1, 3), rvec, t, K, np.zeros(5))[0].reshape(-1, 2)

def render(rvec, t, can_xy=None, seed=0, distractor=True):
    rng = np.random.default_rng(seed)
    img = np.empty((H, W, 3), np.uint8); img[:] = (60, 120, 190)            # wood-ish BGR
    img = np.clip(img.astype(int) + rng.integers(-6, 7, img.shape), 0, 255).astype(np.uint8)
    for c in table_corners():                                               # tape X: two 7 cm strokes, 6 mm wide
        for ang in (np.pi / 4, -np.pi / 4):
            d = 0.035 * np.array([np.cos(ang), np.sin(ang)])
            a, b = project(rvec, t, [[*(c - d), 0], [*(c + d), 0]]).astype(int)
            cv2.line(img, tuple(a), tuple(b), (60, 220, 200), 4)             # yellow-green in BGR (H~33)
    if distractor:                                                           # a yellow blob (snack bag) that is not an X
        cv2.ellipse(img, (1000, 150), (60, 30), 0, 0, 360, (60, 220, 200), -1)
    if can_xy is not None:
        ang = np.linspace(0, 2 * np.pi, 60, endpoint=False)
        ring = np.c_[np.cos(ang), np.sin(ang)] * CAN_D / 2 + np.asarray(can_xy)
        pts = np.vstack([np.c_[ring, np.zeros(60)], np.c_[ring, np.full(60, CAN_H)]])
        hull = cv2.convexHull(project(rvec, t, pts).astype(np.float32)).astype(np.int32)
        cv2.fillConvexPoly(img, hull, (30, 90, 240))
    return cv2.GaussianBlur(img, (3, 3), 0)

def test_ordering_is_bl_tl_tr_br():
    rvec, t = make_pose()
    truth = project(rvec, t, np.c_[table_corners(), np.zeros(4)])
    got = order_corners(truth[[2, 0, 3, 1]])            # shuffled input
    assert np.allclose(got, truth, atol=1e-6)
    assert np.allclose(order_corners(truth, rotate=1)[0], truth[1])

def test_markers_and_homography_within_5mm():
    rvec, t = make_pose()
    img = render(rvec, t)
    pts, info = detect_markers(img)
    assert pts is not None, info
    truth = project(rvec, t, np.c_[table_corners(), np.zeros(4)])
    assert np.abs(pts - truth).max() < 2.0              # marker centres within 2 px
    cal = TableCalib(pts, K=K)
    assert np.allclose(cal.pixel_to_table(pts), table_corners(), atol=1e-6)
    # random points on the table plane (inside and a bit outside the square) are reconstructed within 5 mm
    rng = np.random.default_rng(1); xy = rng.uniform(-0.2, 0.2, (200, 2))
    rec = cal.pixel_to_table(project(rvec, t, np.c_[xy, np.zeros(200)]))
    assert np.abs(rec - xy).max() < 0.005
    # elevated points: lifting through the pose model recovers them, projecting on z=0 does not
    up = project(rvec, t, np.c_[xy, np.full(200, 0.0575)])
    assert np.abs(cal.pixel_to_table(up, z=0.0575) - xy).max() < 0.005
    assert np.abs(cal.pixel_to_table(up) - xy).max() > 0.005

def test_squareness_rejects_non_squares():
    rvec, t = make_pose()
    truth = project(rvec, t, np.c_[table_corners(), np.zeros(4)])
    assert squareness(truth, (W, H)) < 0.05
    bad = truth.copy(); bad[1] += [150, -200]
    assert squareness(bad, (W, H)) > 0.2

def test_calibrate_from_frames_vote():
    rvec, t = make_pose()
    frames = [render(rvec, t, can_xy=(-0.1 + 0.2 * i / 9, 0.1), seed=i) for i in range(10)]
    pts, info = calibrate_from_frames(frames)
    truth = project(rvec, t, np.c_[table_corners(), np.zeros(4)])
    assert pts is not None and np.abs(pts - truth).max() < 2.0, info

def test_can_track_within_5mm():
    rvec, t = make_pose()
    bg = render(rvec, t)
    pts, _ = detect_markers(bg)
    cal = TableCalib(pts, K=K)
    ct = CanTracker(cal, background=bg)
    errs = []
    for i, xy in enumerate([(-0.12, -0.12), (-0.12, 0.12), (0.0, 0.14), (0.12, 0.12), (0.12, -0.12), (-0.12, -0.12)]):
        out = ct.update(render(rvec, t, can_xy=xy, seed=10 + i))
        assert out["q"] == Q_OK, (xy, out)
        errs.append(np.hypot(*(np.array(out["xy"]) - xy)))
    assert max(errs) < 0.005, errs

def test_can_hold_when_occluded():
    rvec, t = make_pose()
    bg = render(rvec, t); cal = TableCalib(detect_markers(bg)[0], K=K); ct = CanTracker(cal, background=bg, hold_frames=3)
    ct.update(render(rvec, t, can_xy=(0.05, 0.05)))
    held = ct.update(bg)                                  # can fully hidden
    assert held["q"] == 1 and np.allclose(held["xy"], ct.prev)
    for _ in range(5): out = ct.update(bg)
    assert out["q"] == 0 and np.isnan(out["xy"][0])

def test_process_video_end_to_end(tmp_path):
    from vision.process_video import main
    rvec, t = make_pose()
    path = tmp_path / "take_01.mp4"
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (W, H))
    corners = [(-0.12, -0.12), (-0.12, 0.12), (0.12, 0.12), (0.12, -0.12), (-0.12, -0.12)]
    truth = []
    for i in range(80):
        s, a = divmod(i / 20.0, 1.0); s = int(min(s, 3))
        xy = np.array(corners[s]) * (1 - a) + np.array(corners[s + 1]) * a; truth.append(xy)
        vw.write(render(rvec, t, can_xy=xy, seed=i))
    vw.release()
    t0 = 1_700_000_000.0
    json.dump([t0 + i / 30 for i in range(80)], open(tmp_path / "take_01_frames.json", "w"))
    out = tmp_path / "o.npz"
    main([str(path), "--no-hands", "--hfov", "100", "--out", str(out)])
    z = np.load(out)
    assert z["t_wall"][0] == t0 and len(z["t_wall"]) == 80
    ok = z["can_q"] == Q_OK
    assert ok.mean() > 0.8
    err = np.hypot(*(z["can_xy"][ok] - np.array(truth)[ok]).T)
    assert np.median(err) < 0.005 and err.max() < 0.015, (np.median(err), err.max())   # mp4 compression adds a little noise
