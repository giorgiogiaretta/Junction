# Loaded automatically by Python (winshim is on PYTHONPATH in run_real.ps1).
# G1_FAST=1 (staff-approved on 15/11, operator's request): runner safety filter with arm speed 2.0 rad/s (was 1.0) and NO
# counter keep-out (the table was lowered relative to the robot). Joint limits, hand limits, workspace box and watchdog stay.
import os
if os.environ.get("G1_FAST") == "1":
    try:
        from aaltonomous.interface import safety as _s
        _Orig = _s.SafetyConfig
        def _fast(*a, **k):
            k.setdefault("arm_max_vel", float(os.environ.get("G1_FAST_ARM_VEL", "2.0")))
            k.setdefault("counter_keepout_min", None); k.setdefault("counter_keepout_max", None)
            return _Orig(*a, **k)
        _fast.from_yaml = _Orig.from_yaml
        _s.SafetyConfig = _fast
        print(f"[G1_FAST] runner filter: arm {os.environ.get('G1_FAST_ARM_VEL', '2.0')} rad/s, no counter keep-out", flush=True)
    except Exception as e:
        print("[G1_FAST] not applied:", e, flush=True)
# G1_LOWLAG=1 (start_g1.ps1 -LowLag / run_real.ps1 -LowLag): performance-only patches, see winshim/lowlag.py and
# docs/ARM_DELAY.md (bit-identical fast CRC for rt/lowcmd; no safety rule touched).
if os.environ.get("G1_LOWLAG") == "1":
    try:
        import lowlag
        lowlag.apply()
    except Exception as e:
        print("[G1_LOWLAG] not applied:", e, flush=True)
