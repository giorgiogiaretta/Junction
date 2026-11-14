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


def render_can(cx, cy, r, h, colour):
    """Ray-trace an UPRIGHT cylinder (axis at x=cx, y=cy, from TABLE_Z to TABLE_Z+h, pelvis frame) on the table."""
    us, vs = np.meshgrid(np.arange(W), np.arange(H))
    dirs = np.stack([(us - CX) / FX, (vs - CY) / FY, np.ones_like(us, float)], -1) @ R.T
    o = CAM_T; dx, dy, dz = dirs[..., 0], dirs[..., 1], dirs[..., 2]
    t_tab = np.where(dz < -1e-6, (TABLE_Z - o[2]) / np.minimum(dz, -1e-6), np.inf)
    ox, oy = o[0] - cx, o[1] - cy                                               # side: |(o + t d)_xy - c_xy| = r
    a = dx ** 2 + dy ** 2; b = 2 * (ox * dx + oy * dy); c = ox ** 2 + oy ** 2 - r ** 2
    disc = b ** 2 - 4 * a * c
    t_side = np.where(disc > 0, (-b - np.sqrt(np.maximum(disc, 0))) / (2 * np.maximum(a, 1e-12)), np.inf)
    zs = o[2] + t_side * dz
    t_side = np.where((zs >= TABLE_Z) & (zs <= TABLE_Z + h) & (t_side > 0), t_side, np.inf)
    t_top = np.where(dz < -1e-6, (TABLE_Z + h - o[2]) / np.minimum(dz, -1e-6), np.inf)   # top cap disc
    on_cap = (ox + t_top * dx) ** 2 + (oy + t_top * dy) ** 2 <= r ** 2
    t_top = np.where(on_cap & (t_top > 0), t_top, np.inf)
    t_obj = np.minimum(t_side, t_top); hit = t_obj < t_tab
    t = np.where(hit, t_obj, t_tab)
    depth = np.where(np.isfinite(t), np.round(t * 1000), 0).astype(np.uint16)
    rgb = np.full((H, W, 3), (90, 70, 50), np.uint8); rgb[hit] = colour
    return rgb, depth


@pytest.mark.parametrize("x,y", [(0.38, -0.05), (0.32, 0.08), (0.45, -0.15)])
def test_upright_can_bbox_and_mask_within_1cm(x, y):
    """Standing can seen from ~48 deg above: the centre is r away horizontally (Giorgio's bias fix), not r along the 3D ray."""
    r, h = 0.029, 0.146; c = np.array([x, y, TABLE_Z + h / 2])
    rgb, depth = render_can(x, y, r, h, (40, 90, 200))                          # blue: no colour mask
    can = (rgb == (40, 90, 200)).all(-1); vs, us = np.nonzero(can)
    out = locate(rgb, depth, p2p, label="can", conf=0.8, bbox=[us.min(), vs.min(), us.max(), vs.max()], table_z=TABLE_Z)
    assert out["object"] == "can" and out["conf"] == 0.8 and out["depth_ok"], out
    assert np.linalg.norm(np.array(out["p_pelvis"][:2]) - c[:2]) <= 0.01, (out, c)
    assert abs(out["p_pelvis"][2] - c[2]) < 1e-6                                # snapped to table + half height
    out = locate(rgb, depth, p2p, label="can_empty", mask=can, table_z=TABLE_Z)
    assert out["depth_ok"] and np.linalg.norm(np.array(out["p_pelvis"][:2]) - c[:2]) <= 0.006, (out, c)


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


def test_loose_bbox_on_white_mat_is_refused_not_mislocated():
    """Sim outlier (egg bbox, 10.7 cm): mat depth mixed into the median. Must come back depth_ok=False, never a wrong pose marked ok."""
    c = np.array([0.36, 0.04, TABLE_Z + 0.0215])
    rgb, depth = render(c, (0.0215, 0.0215, 0.0215), (245, 245, 240))
    egg = (rgb == (245, 245, 240)).all(-1); vs, us = np.nonzero(egg)
    rgb[~egg] = (217, 217, 204)                                                 # light mat everywhere: colour cannot separate egg/mat
    cu, cv, hw, hh = us.mean(), vs.mean(), us.max() - us.min(), vs.max() - vs.min()
    loose = [int(cu - 2 * hw), int(cv - 2 * hh), int(cu + 2 * hw), int(cv + 2 * hh)]   # box 4x the egg: core mostly mat
    out = locate(rgb, depth, p2p, label="egg", bbox=loose, table_z=TABLE_Z)
    assert out["depth_ok"] is False, out
    tight = locate(rgb, depth, p2p, label="egg", mask=egg, table_z=TABLE_Z)     # the same frame with a real mask is still accepted
    assert tight["depth_ok"] and np.linalg.norm(np.array(tight["p_pelvis"][:2]) - c[:2]) <= 0.01, tight


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
