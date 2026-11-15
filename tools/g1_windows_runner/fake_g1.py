"""Fake G1 on DDS domain 1 (this PC only, NEVER the robot network): offline reproduction of the arm-lag problem.

Publishes rt/lowstate (hg LowState_, 500 Hz, `tick` = wall ms mod 2^32 so a reader on the same PC can measure the
sample's AGE) and rt/dex3/{left,right}/state (HandState_, --hand-hz each), and makes the 35 joint positions follow the
last rt/lowcmd q with a first-order lag (tau --tau s, a stand-in for the real PD loop). Optional --pad-kbps of extra
traffic on another topic mimics the rest of the robot's multicast traffic that the runner's DDS receive thread must
also drain. Used by lowlag_bench.py. Domain 1 = Unitree's simulation domain; never run this on the robot network.

    py -3.11 tools/g1_windows_runner/fake_g1.py [--seconds 60] [--hand-hz 500] [--pad-kbps 800]
"""
import argparse
import os
import sys
import time

ROOT = r"C:\Users\giorg\Desktop\aaltonomous-humanoid"
if os.path.isdir(ROOT + r"\third_party\cyclonedds\install\bin"):
    os.add_dll_directory(ROOT + r"\third_party\cyclonedds\install\bin")
sys.path[:0] = [ROOT + r"\third_party\unitree_sdk2_python"]

import numpy as np
from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelPublisher, ChannelSubscriber
from unitree_sdk2py.idl.default import unitree_hg_msg_dds__HandState_, unitree_hg_msg_dds__LowState_
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import HandState_, LowCmd_, LowState_


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--hz", type=float, default=500)
    ap.add_argument("--hand-hz", type=float, default=500)
    ap.add_argument("--tau", type=float, default=0.03)
    ap.add_argument("--pad-kbps", type=float, default=0.0, help="extra traffic [kB/s] on rt/fake_pad (LowState msgs)")
    a = ap.parse_args()
    ChannelFactoryInitialize(1)
    pub = ChannelPublisher("rt/lowstate", LowState_); pub.Init()
    hands = []
    for side in ("left", "right"):
        p = ChannelPublisher(f"rt/dex3/{side}/state", HandState_); p.Init(); hands.append(p)
    pad = None
    if a.pad_kbps > 0:
        pad = ChannelPublisher("rt/fake_pad", LowState_); pad.Init()
    q = np.zeros(35); q[15:29] = 0.1
    cmd = {"q": None}
    # lowcmd: non-blocking poll of the raw Cyclone reader in the main loop (a Python listener here would compete for
    # this process's GIL with the 500 Hz loop: the very effect being reproduced on the runner side)
    sub = ChannelSubscriber("rt/lowcmd", LowCmd_); sub.Init()
    reader = sub._ChannelSubscriber__channel._Channel__reader._Reader__reader
    st, hs = unitree_hg_msg_dds__LowState_(), unitree_hg_msg_dds__HandState_()
    st.mode_machine = 5
    dt, k, t0 = 1.0 / a.hz, 0, time.perf_counter()
    hand_every = max(1, int(round(a.hz / a.hand_hz)))
    pad_per_tick = a.pad_kbps * 1000 / 2092 / a.hz
    pad_acc = 0.0
    alpha = 1 - np.exp(-dt / a.tau)
    while time.perf_counter() - t0 < a.seconds:
        got = reader.take(N=8)
        if got:
            m = got[-1]
            cmd["q"] = np.array([m.motor_cmd[i].q for i in range(35)])
        if cmd["q"] is not None:
            q += alpha * (cmd["q"] - q)
        st.tick = int(time.time() * 1000) & 0xFFFFFFFF
        for i in range(35):
            st.motor_state[i].q = float(q[i])
        pub.Write(st)
        if k % hand_every == 0:
            for p in hands:
                p.Write(hs)
        pad_acc += pad_per_tick
        while pad is not None and pad_acc >= 1:
            pad.Write(st); pad_acc -= 1
        k += 1
        nxt = t0 + k * dt
        while True:  # Python 3.11 on Windows: high-resolution sleep
            r = nxt - time.perf_counter()
            if r <= 0:
                break
            time.sleep(r)
    print(f"fake_g1: {k} lowstate msgs in {time.perf_counter() - t0:.1f} s", flush=True)


if __name__ == "__main__":
    main()
