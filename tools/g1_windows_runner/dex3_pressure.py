"""READ ONLY: Dex3 hand sensors of the real G1 (rt/dex3/{left,right}/state). Sends nothing; a separate process from the runner
(own DDS participant, own GIL), so it adds no load to the arm control. Run it in a second terminal, before or during a run.

    py -3.11 tools/g1_windows_runner/dex3_pressure.py [--seconds 120] [--hz 30] [--iface "Ethernet 5"]

Per message, HandState_ carries: motor_state[7] (q, dq, tau_est = estimated motor torque, temperature), press_sensor_state[N]
(N pads, each 12 pressure cells + 12 temperatures + a `lost` counter), imu_state, power.
Measured on the robot 15/11: 9 pads x 12 cells per hand at ~30 Hz; only 4 cells per pad are real (absolute pressure in Pa,
~100 000 = 1 atm at rest), the other 8 read a constant 30000 placeholder. tau_est reads nonsense (up to 5e5): not usable.
Live line per hand: pressure RISE per pad over its rest value (kPa, real cells summed), after 1 s of rest baseline. Everything is logged to data/live/dex3_press_<time>.jsonl (one row per hand per sample, all cells)
and a short summary at the end: per pad the idle baseline (first 2 s), max, and when it rose above baseline + 5 noise sd.
"""
import argparse, json, os, subprocess, sys, time

ROOT_A = r"C:\Users\giorg\Desktop\aaltonomous-humanoid"
if os.path.isdir(ROOT_A + r"\third_party\cyclonedds\install\bin"):
    os.add_dll_directory(ROOT_A + r"\third_party\cyclonedds\install\bin")
sys.path[:0] = [ROOT_A + r"\third_party\unitree_sdk2_python"]
import numpy as np
from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import HandState_

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))


def robot_iface():
    ps = ('(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object IPAddress -like "192.168.123.*" '
          '| Select-Object -First 1).InterfaceAlias')
    return subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout.strip() or None


def raw_reader(sub):  # the Cyclone DataReader behind the SDK wrapper: non-blocking take, no Python listener in the DDS thread
    return sub._ChannelSubscriber__channel._Channel__reader._Reader__reader


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=120); ap.add_argument("--hz", type=float, default=30)
    ap.add_argument("--iface", default=None); ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    iface = a.iface or os.environ.get("G1_IFACE") or robot_iface()
    if not iface: raise SystemExit("no adapter with a 192.168.123.x address: robot cable / IP")
    ChannelFactoryInitialize(0, iface)
    rd = {}
    for side in ("left", "right"):
        s = ChannelSubscriber(f"rt/dex3/{side}/state", HandState_); s.Init(); rd[side] = (s, raw_reader(s))
    os.makedirs(os.path.join(ROOT, "data", "live"), exist_ok=True)
    out = os.path.join(ROOT, "data", "live", time.strftime("dex3_press_%Y%m%d_%H%M%S.jsonl"))
    f = open(out, "w"); print(f"[dex3] {iface}: logging to {out}", flush=True)
    base_acc = {}
    t0 = time.time(); n = {"left": 0, "right": 0}; first = {}; hist = {"left": [], "right": []}; last_print = 0.0
    while time.time() - t0 < a.seconds:
        line = []
        for side, (_, r) in rd.items():
            got = r.take(N=16)
            if not got: continue
            m = got[-1]; n[side] += len(got); t = round(time.time() - t0, 3)
            P = np.array([list(p.pressure) for p in m.press_sensor_state], float)          # [pads, 12]
            T = np.array([list(p.temperature) for p in m.press_sensor_state], float)
            lost = [int(p.lost) for p in m.press_sensor_state]
            tau = np.array([ms.tau_est for ms in m.motor_state], float); q = np.array([ms.q for ms in m.motor_state], float)
            if side not in first:
                first[side] = True
                print(f"[dex3] {side}: {len(m.motor_state)} motors, {P.shape[0]} pressure pads x {P.shape[1] if P.size else 0} cells; "
                      f"first pad raw {P[0].round(1).tolist() if P.size else None}", flush=True)
            hist[side].append((t, np.where(P != 30000.0, P, 0.0).sum(1) if P.size else np.zeros(0)))
            f.write(json.dumps({"t": t, "hand": side, "q": q.round(4).tolist(), "tau_est": tau.round(4).tolist(),
                                "pressure": P.round(2).tolist(), "temp": T.round(1).tolist(), "lost": lost}) + "\n")
            if P.size:
                real = P != 30000.0                                                   # placeholder cells excluded
                Pr = np.where(real, P, 0.0).sum(1)
                if side not in base_acc: base_acc[side] = []
                if t < 1.0: base_acc[side].append(Pr)
                elif base_acc[side]:
                    d = (Pr - np.mean(base_acc[side], 0)) / 1000.0
                    line.append(f"{side[0].upper()} kPa " + " ".join(f"{v:5.1f}" for v in d) + f"  max {d.max():5.1f}")
        if line and not a.quiet and time.time() - last_print > 0.25:
            print("  ".join(line), flush=True); last_print = time.time()
        time.sleep(1 / a.hz)
    f.close()
    print(f"\n[dex3] messages: {n}  ->  {out}")
    for side, h in hist.items():
        if not h or not len(h[0][1]): continue
        ts = np.array([x[0] for x in h]); S = np.array([x[1] for x in h])
        base = S[ts < 1.0] if (ts < 1.0).sum() > 5 else S[:10]; mu, sd = base.mean(0), base.std(0) + 1e-6
        for k in range(S.shape[1]):
            up = np.flatnonzero(S[:, k] > mu[k] + max(5 * sd[k], 200.0))
            print(f"  {side} pad {k}: rest noise sd {sd[k]:.0f} Pa, max rise {(S[:, k].max() - mu[k]) / 1000:.1f} kPa"
                  + (f", above idle from t={ts[up[0]]:.1f}s ({len(up)} samples)" if len(up) else ", never above idle"))


if __name__ == "__main__":
    main()
