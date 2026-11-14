"""READ ONLY: listens to the G1 state topics for 5 s, sends nothing."""
import os, time
os.add_dll_directory(r"C:\Users\giorg\Desktop\aaltonomous-humanoid\third_party\cyclonedds\install\bin")
from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_, HandState_

ChannelFactoryInitialize(0, "Ethernet 5")
got = {"low": 0, "left": 0, "right": 0}; last = {}
def cb(k):
    def f(m): got[k] += 1; last[k] = m
    return f
s1 = ChannelSubscriber("rt/lowstate", LowState_); s1.Init(cb("low"), 10)
s2 = ChannelSubscriber("rt/dex3/left/state", HandState_); s2.Init(cb("left"), 10)
s3 = ChannelSubscriber("rt/dex3/right/state", HandState_); s3.Init(cb("right"), 10)
time.sleep(5)
print("messages in 5 s:", got)
if "low" in last:
    q = [round(last["low"].motor_state[i].q, 3) for i in range(29)]
    print("legs", q[:12]); print("waist", q[12:15]); print("left arm", q[15:22]); print("right arm", q[22:29])
    print("mode_machine", last["low"].mode_machine)
for k in ("left", "right"):
    if k in last: print(k, "hand", [round(last[k].motor_state[i].q, 3) for i in range(7)])

