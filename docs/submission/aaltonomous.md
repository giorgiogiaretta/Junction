# Aaltonomous Humanoid (Aalto) — only what is documented

> **The Aaltonomous task is autonomous sorting** (cubes, cylinders, prisms into three boxes, 2 minutes, Docker policy server). **The repository contains no sorting policy and no sorting result.** Recommendation: do not enter this track unless Giorgio submits a sorting image [DA VERIFICARE]. What follows is what we did with the Aalto G1 as the body of the Rokoko project, usable as context only.

## What we did on the Aalto stack (documented)
- **The organisers' runner on Windows, against the real G1** (`tools/g1_windows_runner/README.md`): CycloneDDS built from source, small shims for Pinocchio and turbojpeg checked against MuJoCo, start-up path accepted by the runner filter (`g1/start_path.py`).
- **Real-robot runs:** gloves drove both arms and Dex3 hands, 2 runs of 120 s at 29.8 commands per second, 0 commands clipped by the safety filter (`g1/arms_simple.py`).
- **Things learned on the real robot** (useful to any team): the rest pose has the wrists inside the counter keep-out, so the first move must go up; the resting left fingers sit past the URDF limits, so every target must be clamped; the arms followed commands with a 0.6-1.4 s delay under load while our policy took 4-8 ms per command (`docs/DELIVERY_G1.md`).
- **Perception for the G1 head RGB-D** (`ai/perceive.py`, `g1/perception_v1.py`): every object on the table with label, position and cap, tested on simulated frames only (egg 24/24, can 23/24, `docs/G1_V1_RUN.md`).

## Not done
No autonomous sorting, no instruction parsing, no Isaac Sim run, no Docker submission, no Hugging Face dataset use.
