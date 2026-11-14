"""ai/locate.py on synthetic head RGB-D renders (ray-traced sphere / ellipsoid on a table). Numpy only, no model, no hardware."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
import numpy as np
import pytest
from ai.locate import locate, FX, FY, CX, CY

H, W = 480, 640
PITCH = np.deg2rad(48.0)                    # camera looks down ~48 deg, like the G1 d435_link
CAM_T = np.array([0.06, 0.0, 0.45])         # camera position in the "pelvis" frame (x forward, y left, z up)
# optical frame (x right, y down, z forward) -> pelvis: forward axis tilted down by PITCH
fwd = np.array([np.cos(PITCH), 0.0, -np.sin(PITCH)]); right = np.array([0.0, -1.0, 0.0]); down = np.cross(fwd, right)
R = np.stack([right, down, fwd], 1)
TABLE_Z = 0.01


def p2p(u, v, d_mm):
    z = d_mm / 1000.0
    return (R @ np.array([(u - CX) * z / FX, (v - CY) * z / FY, z]) + CAM_T).tolist()


def render(centre, radii, colour, axes=np.eye(3)):
    """Ray-trace an ellipsoid (pelvis frame, semi-axes radii along columns of axes) on the table plane z=TABLE_Z."""
    us, vs = np.meshgrid(np.arange(W), np.arange(H))
    dirs = np.stack([(us - CX) / FX, (vs - CY) / FY, np.ones_like(us, float)], -1) @ R.T   # pelvis-frame ray per unit z-depth
    o = CAM_T
    # table: o_z + t*dir_z = TABLE_Z
    t_tab = np.where(dirs[..., 2] < -1e-6, (TABLE_Z - o[2]) / np.minimum(dirs[..., 2], -1e-6), np.inf)
    S = axes / np.asarray(radii)             # map to unit sphere: q = S^T (p - c)
    oc = S.T @ (o - centre); dd = dirs @ S
    a = (dd ** 2).sum(-1); b = 2 * (dd @ oc); c = oc @ oc - 1
    disc = b ** 2 - 4 * a * c
    t_obj = np.where(disc > 0, (-b - np.sqrt(np.maximum(disc, 0))) / (2 * a), np.inf)
    hit = t_obj < t_tab
    t = np.where(hit, t_obj, t_tab)
    depth = np.where(np.isfinite(t), np.round(t * 1000), 0).astype(np.uint16)   # t is z-depth because dirs have unit optical z
    rgb = np.full((H, W, 3), (90, 70, 50), np.uint8); rgb[hit] = colour
    return rgb, depth


@pytest.mark.parametrize("x,y", [(0.35, 0.0), (0.40, 0.10), (0.30, -0.12)])
def test_ball_centre_within_1cm(x, y):
    r = 0.0325; c = np.array([x, y, TABLE_Z + r])
    rgb, depth = render(c, (r, r, r), (240, 120, 30))
    out = locate(rgb, depth, p2p)
    assert out["object"] == "stress_ball" and out["depth_ok"] and out["frame"] == "pelvis"
    err = np.abs(np.array(out["p_pelvis"]) - c)
    assert err[0] <= 0.01 and err[1] <= 0.01 and err[2] <= 0.015, (out, c)
    snapped = locate(rgb, depth, p2p, table_z=TABLE_Z)
    assert abs(snapped["p_pelvis"][2] - c[2]) < 1e-6


def test_lying_egg_centre_and_axis():
    ang = np.deg2rad(30); ax = np.array([np.cos(ang), np.sin(ang), 0.0])
    axes = np.stack([ax, np.cross([0, 0, 1], ax), [0, 0, 1]], 1)
    c = np.array([0.36, 0.04, TABLE_Z + 0.0215])
    rgb, depth = render(c, (0.0285, 0.0215, 0.0215), (245, 245, 240), axes)
    out = locate(rgb, depth, p2p, table_z=TABLE_Z)
    assert out["object"] == "egg" and out["depth_ok"]
    err = np.abs(np.array(out["p_pelvis"]) - c); assert err[0] <= 0.01 and err[1] <= 0.01, (out, c)
    a = np.array(out["axis_pelvis"]); a_xy = a[:2] / np.linalg.norm(a[:2])
    assert abs(a_xy @ ax[:2]) > np.cos(np.deg2rad(15)), (a, ax)   # long axis within 15 deg in the table plane


def test_given_bbox_and_label_without_colour_support():
    r = 0.029; c = np.array([0.38, -0.05, TABLE_Z + r])
    rgb, depth = render(c, (r, r, r), (40, 90, 200))   # blue: no colour mask
    vs, us = np.nonzero((rgb == (40, 90, 200)).all(-1))
    out = locate(rgb, depth, p2p, label="can", conf=0.8, bbox=[us.min(), vs.min(), us.max(), vs.max()])
    assert out["object"] == "can" and out["conf"] == 0.8
    err = np.abs(np.array(out["p_pelvis"]) - c); assert err[0] <= 0.01 and err[1] <= 0.01, (out, c)


def test_big_white_mat_is_not_an_egg_and_mask_param():
    c = np.array([0.36, 0.04, TABLE_Z + 0.0215])
    rgb, depth = render(c, (0.0215, 0.0215, 0.0215), (245, 245, 240))
    egg = (rgb == (245, 245, 240)).all(-1)
    mat = np.zeros_like(egg); mat[300:480, 100:540] = True; mat &= ~egg      # light mat (sim: rgba 0.85) under the egg
    rgb[mat] = (217, 217, 204)
    out = locate(rgb, depth, p2p)                                               # mat + egg = one huge white blob -> refused, not mislocated
    assert out["p_pelvis"] is None or np.linalg.norm(np.array(out["p_pelvis"][:2]) - c[:2]) <= 0.01
    out = locate(rgb, depth, p2p, mask=egg, label="egg")                        # detector mask: correct
    assert out["object"] == "egg" and np.linalg.norm(np.array(out["p_pelvis"][:2]) - c[:2]) <= 0.01, out
    assert locate(rgb, depth, p2p, mask=np.zeros_like(egg))["p_pelvis"] is None


def test_bench_adapter_frame_conversion():
    from ai.locate_bench import pixel_to_world
    pos = np.array([0.1, 0.2, 0.3]); Rm = np.eye(3)                              # MuJoCo camera looking along world -z
    p = pixel_to_world((pos, Rm))(CX, CY, 500)
    assert np.allclose(p, [0.1, 0.2, -0.2])
    p = pixel_to_world((pos, Rm))(CX + FX, CY + FY, 1000)                        # right and down in the image
    assert np.allclose(p, [1.1, -0.8, -0.7])


def test_no_object_and_no_depth_are_flagged():
    rgb = np.full((H, W, 3), (90, 70, 50), np.uint8); depth = np.zeros((H, W), np.uint16)
    assert locate(rgb, depth, p2p)["p_pelvis"] is None
    r = 0.0325; rgb2, _ = render(np.array([0.35, 0, TABLE_Z + r]), (r, r, r), (240, 120, 30))
    out = locate(rgb2, depth, p2p); assert out["p_pelvis"] is None and out["depth_ok"] is False


def test_fast_enough():
    import time
    r = 0.0325; rgb, depth = render(np.array([0.35, 0, TABLE_Z + r]), (r, r, r), (240, 120, 30))
    t = time.time(); locate(rgb, depth, p2p); assert time.time() - t < 0.1
