"""Synthetic aligned RGB-D fixtures; no model downloads or hardware."""
import numpy as np
import pytest
from cv.locate import locate
from ai.locate import camera_point


@pytest.fixture
def scene():
    rgb = np.zeros((480, 640, 3), dtype=np.uint8)
    depth = np.zeros((480, 640), dtype=np.uint16)
    mask = np.zeros((480, 640), dtype=bool)
    mask[220:260, 290:350] = True
    rgb[mask] = 220
    depth[mask] = 600
    return rgb, depth, mask


def calibration(u, v, depth_mm):
    # Synthetic optical-to-pelvis translation, not the actual G1 calibration.
    return np.asarray(camera_point(u, v, depth_mm)) + [1, 2, 3]


def test_requires_calibration_and_explicit_localization_evidence(scene):
    rgb, depth, mask = scene
    result = locate(rgb, depth, label="egg", mask=mask)
    assert not result["depth_ok"] and result["p_pelvis"] is None
    assert result["frame"] is None
    result = locate(rgb, depth, calibration)
    assert result["object"] == "unknown" and not result["depth_ok"]


def test_known_mask_delegates_geometry_in_calibrated_frame(scene):
    rgb, depth, mask = scene
    result = locate(rgb, depth, calibration, label="egg", conf=.8, mask=mask)
    assert result["depth_ok"] and result["frame"] == "pelvis"
    assert np.allclose(result["p_surface"], [1., 2., 3.6], atol=.0011)
    assert np.isclose(result["p_pelvis"][2], 3.6215, atol=.0001)
    assert result["axis_pelvis"] is not None
    assert result["object"] == "egg" and result["conf"] == .8


def test_bbox_half_open_conversion_and_no_axis_from_rectangle(scene):
    rgb, depth, _ = scene
    result = locate(rgb, depth, calibration, label="egg", bbox=[290, 220, 350, 260])
    assert result["depth_ok"]
    assert result["bbox"] == [290, 220, 350, 260]
    assert result["axis_pelvis"] is None


def test_detector_receives_rgb_and_selects_highest_accepted_box(scene):
    rgb, depth, _ = scene
    def detector(image):
        assert image.mode == "RGB" and image.size == (640, 480)
        return [{"label": "can", "score": .2, "bbox": [1, 1, 3, 3]},
                {"label": "egg", "score": .8, "bbox": [290, 220, 350, 260]}]
    result = locate(rgb, depth, calibration, detector=detector)
    assert result["depth_ok"] and result["object"] == "egg"
    assert result["evidence"] == "detector_bbox"
    assert result["axis_pelvis"] is None


@pytest.mark.parametrize("detector", [lambda image: [], lambda image: [{"label":"egg", "score": .1, "bbox":[1,1,2,2]}],
                                     lambda image: [{"label":"other", "score": .99, "bbox":[1,1,2,2]}]])
def test_detector_failure_or_rejection_stays_unknown(scene, detector):
    rgb, depth, _ = scene
    result = locate(rgb, depth, calibration, detector=detector)
    assert not result["depth_ok"] and result["object"] == "unknown"
    assert result["p_pelvis"] is None


def test_detector_exception_does_not_return_geometry(scene):
    def broken(image):
        raise RuntimeError("failed model")
    result = locate(*scene[:2], calibration, detector=broken)
    assert not result["depth_ok"] and "detector failed" in result["why"]


@pytest.mark.parametrize("bad_calibration", [lambda u,v,d: [np.nan,0,0], lambda u,v,d: [0,0,0], lambda u,v,d: [1,2]])
def test_broken_calibration_never_leaks_coordinates(scene, bad_calibration):
    result = locate(*scene[:2], bad_calibration, label="egg", mask=scene[2])
    assert not result["depth_ok"] and result["p_pelvis"] is None


@pytest.mark.parametrize("box", [[-1,0,20,20], [0,0,641,480], [10,10,5,20], [0,0,np.nan,20]])
def test_invalid_boxes_rejected(scene, box):
    result = locate(*scene[:2], calibration, label="egg", bbox=box)
    assert not result["depth_ok"] and result["p_pelvis"] is None


def test_invalid_depth_mask_and_uncertain_geometry_rejected(scene):
    rgb, depth, mask = scene
    assert not locate(rgb, depth.astype(float), calibration, label="egg", mask=mask)["depth_ok"]
    assert not locate(rgb, depth, calibration, label="egg", mask=mask.astype(np.uint8))["depth_ok"]
    assert not locate(rgb, np.zeros_like(depth), calibration, label="egg", mask=mask)["depth_ok"]
    depth[220:240, 290:350] = 1000
    result = locate(rgb, depth, calibration, label="egg", mask=mask)
    assert not result["depth_ok"]
    assert result["p_pelvis"] is None  # ai.locate returns coordinates even when IQR fails; adapter clears them


def test_mask_bbox_no_overlap_rejected(scene):
    result = locate(*scene[:2], calibration, label="egg", mask=scene[2], bbox=[0,0,20,20])
    assert not result["depth_ok"]


@pytest.mark.parametrize("explicit, expected", [(None, "can"), ("can_empty", "can_empty")])
def test_detector_cannot_establish_can_emptiness(scene, explicit, expected):
    def detector(image):
        return [{"label": "can_empty", "score": .9, "bbox": [290, 220, 350, 260]}]
    result = locate(*scene[:2], calibration, label=explicit, detector=detector)
    assert result["depth_ok"] and result["object"] == expected
