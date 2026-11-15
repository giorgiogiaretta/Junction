# Verda Compute Track

**Pitch:** keep the robot's eyes on infrastructure we control, in the EU. A robot hand that cannot feel needs two independent model families to agree before it squeezes, and one of those families runs on our own Verda GPU.

## What we ran on Verda
| Verda product | What for | Why this product |
|---|---|---|
| **NVIDIA Nemotron endpoint** (hosted by Verda with NVIDIA) | The real-time eyes: one head-camera frame → object, **median 0.22 s**, 48/50 on our photos | Zero setup, fast enough to sit before the grasp |
| **GPU instance (A100)** | **PaliGemma 2 3B, open weights, self-hosted**: the second model family; **49/50, median 0.24 s**, no quota, photos never leave our instance | The Google API free tier gave 20 requests per day per model and took seconds per call; on our own GPU there is no quota and we measure real latency (`docs/VERDA_GEMMA.md`) |

Path from idea to prototype: Google API Gemma (49/50 but ~7.7 s and a daily quota) → `tools/serve_gemma.sh` (vLLM) → `tools/paligemma_server.py` on the A100 through an SSH tunnel, never exposed to the internet → `ai/paligemma.py` plugged into the vote → offline check `python3 -m verify.run`.

## Honest scale of the ambition
We did not train a policy or run thousands of rollouts on Verda. Compute here buys **independence and privacy**, not scale: a second model family we host ourselves, so the safety vote does not depend on one vendor's endpoint or one free quota. GPU type and credits spent are not recorded in the repo [DA VERIFICARE].

## Path to scale
One self-hosted vision model per robot cell, behind an auto-scaling container; the same two-family vote for every gripper; recorded demonstrations labelled automatically and stored in the EU for policy training. Not built yet.
