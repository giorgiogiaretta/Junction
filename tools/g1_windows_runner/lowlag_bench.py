"""Offline reproduction of the real-robot arm lag, against fake_g1.py on DDS domain 1 (this PC only).

Builds the same threads the organisers' runner has on the real robot (aaltonomous DDSBackend): xr_teleoperate's
G1_29_ArmController in REAL mode (simulation_mode=False, so the 250 Hz CRC + velocity clip on measured q run), wrapped
by aaltonomous' make_safe_arm_controller; Dex3 state listeners (queueLen 10) and the 100 Hz hand publisher; optional
camera-like load (JPEG decode + resize, 3 streams at 30 Hz); the 30 Hz command loop (square steps on the arm joints).
Measures the AGE of every rt/lowstate sample the arm controller reads (fake_g1 stamps `tick` with wall ms), the 30 Hz
loop period, and the command -> measured lag (lag_report.py estimators). Writes an npz in the runner's format.

    py -3.11 tools/g1_windows_runner/fake_g1.py --seconds 50 &
    py -3.11 tools/g1_windows_runner/lowlag_bench.py --seconds 40 [--lowlag] [--cams]
--lowlag applies winshim/lowlag.py (what G1_LOWLAG=1 does in the real runner via sitecustomize).
"""
import argparse
import os
import sys
import threading
import time
from pathlib import Path

ROOT = r"C:\Users\giorg\Desktop\aaltonomous-humanoid"
HERE = Path(__file__).resolve().parent
if os.path.isdir(ROOT + r"\third_party\cyclonedds\install\bin"):
    os.add_dll_directory(ROOT + r"\third_party\cyclonedds\install\bin")
sys.path[:0] = [str(HERE / "winshim"), str(HERE), ROOT, ROOT + r"\third_party\xr_teleoperate",
                ROOT + r"\third_party\unitree_sdk2_python"]

import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=40)
    ap.add_argument("--lowlag", action="store_true")
    ap.add_argument("--cams", action="store_true", help="add camera-like decode load (3 x 30 Hz JPEG 640x480)")
    ap.add_argument("--amp", type=float, default=0.5, help="square step amplitude [rad]")
    ap.add_argument("--period", type=float, default=3.0, help="square period [s]")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.lowlag:
        import lowlag
        lowlag.apply()
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelPublisher, ChannelSubscriber
    from unitree_sdk2py.idl.default import unitree_hg_msg_dds__HandCmd_
    from unitree_sdk2py.idl.unitree_hg.msg.dds_ import HandCmd_, HandState_
    from teleop.robot_control.robot_arm import G1_29_ArmController
    from aaltonomous.interface.backends import make_safe_arm_controller
    import lag_report

    ChannelFactoryInitialize(1)
    arm = make_safe_arm_controller(G1_29_ArmController)(motion_mode=False, simulation_mode=False)
    arm.arm()
    ages = []
    sub = arm.lowstate_subscriber
    orig_read = sub.Read

    def read_with_age(*k, **kw):  # same Read, plus the sample's age (fake_g1 tick = its wall ms)
        m = orig_read(*k, **kw)
        if m is not None:
            ages.append(((int(time.time() * 1000) & 0xFFFFFFFF) - m.tick) & 0xFFFFFFFF)
        return m
    sub.Read = read_with_age

    hand_state = np.zeros(14)

    def on_hand(k, m):
        hand_state[7 * k: 7 * k + 7] = [m.motor_state[i].q for i in range(7)]
    keep = []
    pubs = {}
    for k, side in enumerate(("left", "right")):
        p = ChannelPublisher(f"rt/dex3/{side}/cmd", HandCmd_); p.Init()
        s = ChannelSubscriber(f"rt/dex3/{side}/state", HandState_); s.Init(lambda m, k=k: on_hand(k, m), 10)
        keep.append(s); pubs[side] = (p, unitree_hg_msg_dds__HandCmd_())
    stop = threading.Event()

    def hand_loop():
        while not stop.is_set():
            for side, (p, msg) in pubs.items():
                for i in range(7):
                    msg.motor_cmd[i].q = 0.0
                p.Write(msg)
            time.sleep(0.01)
    threading.Thread(target=hand_loop, daemon=True).start()

    if a.cams:
        import cv2
        jpg = cv2.imencode(".jpg", (np.random.rand(480, 640, 3) * 255).astype(np.uint8))[1].tobytes()

        def cam_loop():
            while not stop.is_set():
                for _ in range(3):
                    img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                    cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), (640, 480))
                time.sleep(1 / 30)
        threading.Thread(target=cam_loop, daemon=True).start()

    q0 = np.asarray(arm.get_current_dual_arm_q(), float).copy()
    rows = {"t": [], "wall": [], "arm_q": [], "arm_q_cmd": [], "clipped": [], "mode": []}
    dt, t0, k = 1 / 30, time.monotonic(), 0
    while time.monotonic() - t0 < a.seconds:
        t = time.monotonic() - t0
        cmd = q0 + (a.amp if (t % a.period) < a.period / 2 else 0.0) * (t > 2)
        arm.ctrl_dual_arm(cmd, np.zeros(14))
        rows["t"].append(t); rows["wall"].append(t); rows["arm_q_cmd"].append(cmd.copy())
        rows["arm_q"].append(np.asarray(arm.get_current_dual_arm_q(), float))
        rows["clipped"].append(False); rows["mode"].append(0)
        k += 1
        time.sleep(max(0.0, t0 + k * dt - time.monotonic()))
    stop.set()
    out = Path(a.out or HERE / f"bench_{'lowlag' if a.lowlag else 'base'}{'_cams' if a.cams else ''}" / "episode_000.npz")
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out, **{k_: np.asarray(v) for k_, v in rows.items()})
    r = lag_report.analyse(out, 10.0)
    ag = np.asarray(ages[len(ages) // 10:], float)
    print(f"RESULT lowlag={a.lowlag} cams={a.cams}: lowstate age ms median {np.median(ag):.0f} p95 "
          f"{np.percentile(ag, 95):.0f} max {ag.max():.0f} (reads {len(ages) / a.seconds:.0f}/s); loop p95 "
          f"{r['per_p95']} ms; lag_xc {r.get('lag_xc')} s lag_fit {r.get('lag_fit')} s err_med {r.get('err_med')} "
          f"win {r.get('win')}", flush=True)
    os._exit(0)  # DDS threads are daemons; skip slow interpreter teardown


if __name__ == "__main__":
    main()
