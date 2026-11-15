# G1 real-robot arm delay (~1 s): cause and fix

Status 15/11: root cause found and reproduced offline; fix ready behind `-LowLag` (default OFF). **Not yet run on the robot.**

## 1. Measurements (real runs)

`py -3.11 tools/g1_windows_runner/lag_report.py --backend real --md` (all runs in `aaltonomous-humanoid/runs/giorgio`;
`arm_q_cmd` = the runner's post-filter command, `arm_q` = what rt/lowstate told the runner process).
`lag_xc` = velocity cross-correlation (motion onset); `lag_fit` = delay that best aligns positions (offset removed; with a
rate-limited arm it is larger than the onset delay); `win` = lag_fit per 20 s window. Loop period columns in ms.

| run | dur s | Hz | loop med | loop p95 | loop max | lag_xc s | lag_fit s | err med rad | err p95 rad | clips |
|---|---|---|---|---|---|---|---|---|---|---|
| 20261114_213611 | 120 | 30.0 | 31 | 62 | 110 | 0.61 | 1.24 | 0.086 | 0.25 | 0 |
| 20261114_233643 | 117 | 27.6 | 31 | 63 | 156 | - | 1.75 | 0.081 | 0.30 | 1 |
| 20261114_235630 | 247 | 18.3 | 47 | 94 | 235 | - | 2.47 | 0.051 | 0.32 | 0 |
| 20261115_000423 | 71 | 21.6 | 47 | 93 | 203 | 1.30 | 2.99 (search limit) | 0.051 | 0.66 | 0 |
| 20261115_001115 | 153 | 24.7 | 46 | 63 | 140 | - | 2.99 (search limit) | 0.136 | 0.69 | 0 |
| 20261115_002247 | 101 | 30.0 | 31 | 47 | 78 | 0.70 | 2.08 | 0.080 | 0.53 | 0 |
| 20261115_003217 | 82 | 30.0 | 31 | 47 | 63 | 0.60 | 2.27 | 0.086 | 0.53 | 0 |

(Runs where the arms did not move, or shorter than 5 s, are omitted.) Every mock run: lag 0.00 s, error <= 0.02 rad.
Signature in the plots: the measured joints move in **steps of <= 0.12 rad about once per second**, or ramp at ~0.14 rad/s,
while `arm_q` still changes on every tick, so the readings are old rather than frozen.

## 2. Root cause

1. On Windows, `unitree_sdk2py/utils/crc.py` computes the rt/lowcmd CRC with a **pure-Python bit loop** (`_crc_py`);
   the C library is loaded only on Linux. Measured cost: **1.94 ms per message**. xr_teleoperate's arm thread sends
   250 messages/s, so this takes about **half a core while holding the GIL**. Other GIL users in the same process:
   LowState deserialize 0.5 ms, LowCmd serialize 0.33 ms, Dex3 listeners, the hand thread, cameras, and the 30 Hz loop.
2. Cyclone runs the Python Dex3-state listeners **synchronously in its single receive thread**
   (`SynchronousDeliveryLatencyBound = inf` in `C:\tmp\cdds.LOG`), so that thread waits for the GIL. It then drains the
   socket more slowly than the robot fills it. The **1 MiB socket receive buffer** (same log) fills up, and every
   rt/lowstate sample read is **0.6-1.3 s old**.
3. `G1_29_ArmController` clips each 4 ms target to `measured q +- 30 rad/s * 4 ms = 0.12 rad`. When "measured" is
   ~1 s old, the arm can only move <= 0.12 rad per staleness period. That produces the staircase, the ~0.1 rad steady
   error, and the extra delay the operator feels.

**Offline reproduction:** `tools/g1_windows_runner/fake_g1.py` publishes a fake G1 on DDS domain 1 (500 Hz lowstate with
a wall-clock `tick`, Dex3 states, first-order joints following lowcmd, plus 800 kB/s of extra traffic).
`lowlag_bench.py` builds the runner's threads (the real `G1_29_ArmController` with CRC and clip, aaltonomous
`make_safe_arm_controller`, Dex3 listeners, a 100 Hz hand publisher, camera-like JPEG load, the 30 Hz loop) and measures
each lowstate sample's age directly:

| bench (35 s, camera load on) | lowstate age med / p95 / max ms | cmd -> measured lag (fit) | err med rad |
|---|---|---|---|
| baseline (today's runner) | **610 / 1281 / 1838** | **1.0 s** (every window) | 0.28 |
| `G1_LOWLAG=1` (fast CRC + 1 ms GIL switch) | **3 / 5 / 16** | **0.10 s** (= fake plant tau + 30 Hz sampling) | 0.00 |
| fast CRC only | 3 / 5 / 10 | 0.10 s | 0.00 |
| fast CRC, no camera load | 3 / 4 / 8 | 0.10 s | 0.00 |

The baseline reproduces the real logs: same staleness, steps of the clip size, ~1 s lag. The CRC fix alone removes it.

Ruled out: reader backlog (rt/lowstate reader is Cyclone's default KEEP_LAST 1); a blocking hand queue (`BQueue.Put`
drops when full); low gains (the mock and the fixed bench track in 0.1 s with the same clip); the policy (4-8 ms,
and `arm_q_cmd` is the runner's own post-filter command).

## 3. What changed (all behind `-LowLag`, default OFF)

- `tools/g1_windows_runner/winshim/lowlag.py`: replaces `CRC._crc_py` with a zlib-based CRC-32/MPEG-2 that is
  **bit-identical** (0.003 ms instead of 1.94 ms; the whole `Crc()` call drops to 0.125 ms because of packing). At
  startup it checks itself against the original on 300+ random inputs and a real hg LowCmd; on any mismatch it keeps
  the original. An optional `G1_LOWLAG_SWITCH=0.001` lowers the GIL switch interval; it is off by default because it
  added nothing offline.
- `winshim/sitecustomize.py`: loads `lowlag` when `G1_LOWLAG=1`. `winshim/run_real.ps1 -LowLag` sets that variable;
  `start_g1.ps1 -LowLag` passes it through and now copies this checkout's `winshim/*.py` and `run_real.ps1` into
  `aaltonomous-humanoid\winshim\` (where the runner loads them).
- **No safety rule touched:** joint limits, the runner SafetyFilter (1 rad/s, or 2 rad/s with the staff-approved
  `-Fast`), keep-out, workspace, watchdog, self-collision, and the 30 rad/s clip are unchanged, and the organisers'
  files are not edited. Only the CRC computation is faster, with an identical result.
- New tools: `lag_report.py`, `fake_g1.py`, `lowlag_bench.py`; test `tests/test_lowlag_crc.py`.
- Coil seated calibration: unchanged, it already runs before every `-Coil`/`-CoilVision` start unless `-NoCalib`
  (`start_g1.ps1`; `-CoilVision` sets `-Coil`, and both policies read the same `data/arm_calib.json`).

Offline checks: mock runner with `-LowLag -Fast` (`G1_LOWLAG=1 G1_FAST=1`, replay policy) gave 28.29 Hz command rate
and 0 clipped steps; the CRC tests pass; full pytest has 209 passed. The 3 failures are `test_cv_eval` and
`test_judge_gemini` (known, PC-only) and `test_live_policy_v1`, which only fails in a worktree without the untracked
`data/g1sim` assets.

## 4. Next robot test (exact command)

```
& C:\Users\giorg\Desktop\Junction\start_g1.ps1 -Coil -Fast -LowLag
```
(run from a checkout of this branch; drop `-Fast` for the standard 1 rad/s cap). The runner window must print
`[G1_LOWLAG] fast CRC on (305 self-checks equal)`. If it prints `NOT applied`, stop: the CRC is unchanged and the
run is a plain baseline. After the run: `py -3.11 tools/g1_windows_runner/lag_report.py --backend real`. Expected:
lag_xc around 0.1-0.2 s, no 0.12 rad staircase, loop p95 back near 31-47 ms.
A/B: the same movement without `-LowLag` right before, to compare.

## 5. Still unverified / next options

- Not run on the robot yet. The real robot's PD response (kp 80, kd 3) adds its own delay; it should be tens of ms.
- If lag remains on the robot, the next steps by gain/risk are:
  (a) `-NoCamera` (less load);
  (b) `G1_LOWLAG_SWITCH=0.001`;
  (c) move the Dex3 listeners to a polling thread (a winshim patch of DDSBackend) so no Python code runs in Cyclone's
  receive thread;
  (d) run the runner on Linux, where the SDK uses the C CRC. Steps: boot Ubuntu 22.04 (live USB or a staff Linux
  laptop); `sudo ip addr add 192.168.123.222/24 dev <eth>`; copy `aaltonomous-humanoid`; build Cyclone DDS 0.10.x
  (`git clone -b releases/0.10.x https://github.com/eclipse-cyclonedds/cyclonedds && cmake -B build -DCMAKE_INSTALL_PREFIX=$HOME/cdds && cmake --build build --target install`);
  `export CYCLONEDDS_HOME=$HOME/cdds`; `pip install -e third_party/unitree_sdk2_python` plus the organisers' requirements;
  run `python -m aaltonomous.deploy.runner --backend real --policy ws://<windows-ip>:8000 --team giorgio --network-interface <eth>`.
  The glove/Coil policy stays on Windows (start it with `--host 0.0.0.0`), and both machines must reach each other.
  Not tried.
- Raising the policy CHUNK is not needed: the policy takes 4-8 ms per target.

Reviewers: Codex (independent review plus a table-CRC draft; agreed on the cause; its table CRC and ours match on 3000
random inputs; it flagged that the stale-sample claim needed direct proof, which the bench now gives). DeepSeek (zlib
mapping proof plus a ranked list; its suggested "blocking BQueue" turned out to be non-blocking).
