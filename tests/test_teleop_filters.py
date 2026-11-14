"""Tests for teleoperation smoothing and wrist safety limits."""

import json
from pathlib import Path

import numpy as np

from g1.teleop_filters import OneEuro, QuatFilter, clamp_wrist_to_human, deadband


def test_one_euro_step_converges_and_reduces_noise():
    filt = OneEuro(freq=30)
    values = [filt([0, 0, 0], i / 30) for i in range(5)]
    values += [filt([1, 0, 0], i / 30) for i in range(5, 35)]
    assert abs(values[-1][0] - 1) < 0.01
    rng = np.random.default_rng(4)
    raw = rng.normal(0, 0.01, size=(600, 3))
    filt.reset()
    filtered = np.array([filt(x, i / 30) for i, x in enumerate(raw)])
    assert np.std(filtered[100:]) <= np.std(raw[100:]) / 3


def test_quaternion_filter_keeps_sign_continuity():
    filt = QuatFilter()
    q = np.array([1.0, 0.0, 0.0, 0.0])
    first = filt(q)
    second = filt(-q)
    assert np.dot(first, second) > 0


def test_deadband_suppresses_small_noise_and_passes_motion():
    deadband._held = None
    origin = deadband(np.zeros(3))
    assert np.array_equal(deadband([0.002, 0, 0]), origin)
    assert np.allclose(deadband([0.01, 0, 0]), [0.01, 0, 0])
    deadband._held = None


def test_wrist_clamp_stays_inside_filter_bounds():
    limits = json.loads((Path(__file__).parents[1] / "docs/g1_dex3_limits.json").read_text())
    for angles in ([100, -100, 45], [-100, 100, -90], [70, 70, 70]):
        result = clamp_wrist_to_human([0, 0, 0], angles, limits)
        assert result.shape == (3,)
        assert np.all(np.abs(result) <= np.deg2rad(70) + 1e-12)
        for value, suffix in zip(result, ("wrist_roll_joint", "wrist_pitch_joint", "wrist_yaw_joint")):
            bounds = [x["filter"] for x in limits["arm_q"] if x["joint"].endswith(suffix)]
            assert all(low - 1e-12 <= value <= high + 1e-12 for low, high in bounds)
