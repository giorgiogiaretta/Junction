from ml.grasp_assist import GraspAssist, simulate


def test_assist_reduces_peak_force():
    assert simulate(True) < 0.5 * simulate(False)


def test_open_loop_profile_caps_and_no_sensor():
    ga = GraspAssist(profile="egg")
    out, cap = ga.apply([1.0, 0.2])
    assert cap == 0.5 and out == [0.5, 0.2]
