# Machines and who runs what
| | Giorgio: MSI laptop | Tommaso: MacBook Pro M2 |
|---|---|---|
| Compute | NVIDIA RTX 5070 Ti Laptop, 12 GB VRAM, CUDA (torch 2.11+cu128, Python 3.11) | Apple Silicon, Metal (torch `mps`) or CPU, unified memory (size not verified) |
| Runs | Rokoko SDK driver (Windows) + gloves + Coil Pro, take recording, calibration, model TRAINING (BC/ACT-size) | MuJoCo sim, replay of episodes, dashboard, retarget, Inspire hand, pitch, API calls (Nemotron/Gemini) |
| Notes | Use `py -3.11` for torch/mujoco/pyqtgraph; `python` may be 3.12 (stdlib-only scripts) | MuJoCo viewer needs `mjpython`; headless is fine for tests/CI. Rokoko driver on macOS: NOT verified, so no live gloves here: use `Rokoko/src/replay_rgmp.py` with the committed takes |
- Device pick: `ml/device.py` (CUDA > MPS > CPU). Keep models small enough for both: the baseline trains in ~2 s on the MSI.
- Data flow: raw takes are recorded on Giorgio's PC and committed (data/raw, data/episodes); everything else runs on both machines from those files.
- Do not train big models on the Mac; do not depend on CUDA-only ops in shared code.
