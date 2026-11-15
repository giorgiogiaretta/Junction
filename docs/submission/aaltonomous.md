# Submission 2 — Aaltonomous Humanoid (separate, independent)

**Owner: Giorgio.** This is a **separate project submission** for the Aaltonomous challenge (autonomous sorting with the Unitree G1). It must not reuse the text, numbers or video of the Rokoko submission, and the Rokoko submission does not mention it. The two only share parts of the robot code (see the end of this page).

**Status (15/11 morning): the sorting policy is not in the repository yet.** Every field below marked [FILL] must be filled from Giorgio's actual work; anything not done stays out of the form.

## Form fields
- **Project name:** [FILL]
- **Punchline:** [FILL]
- **Short description (~120 words):** [FILL] What the policy does on the sorting task: which level (1 fixed sorting / 2 sort by instruction / 3 lid), how it sees the objects, how it picks and places.
- **Challenge:** Aaltonomous Humanoid (Aalto University)
- **Docker image submitted:** [FILL] name/tag, built on `aalto-sim:v1`, linux/amd64, policy server at 30 Hz
- **Simulation result (gate for the Top 5 live run):** [FILL] objects sorted per episode, safety checks passed (no crashes, no joint/speed violations, >= 27 Hz)
- **Video (public, max 2:00):** [FILL] its own video, not the Rokoko one
- **Code link:** [FILL] path or branch with the sorting policy

## Linked technology challenges (link only what was really used)
| Technology challenge | Link if… | Evidence to cite [FILL] |
|---|---|---|
| **Verda Compute Track** | Isaac Sim ran on a Verda RTX-class instance (A100/H100 cannot render Isaac Sim), or a policy was trained/evaluated there | instance type, hours, what ran |
| **NVIDIA: Best Use of Nemotron** | Nemotron parses the text instruction (level 2) or plans the sort | prompt, examples, how output was checked |
| **Google DeepMind: Best Use of Gemma** | a Gemma model runs **inside the Docker image** (the evaluation machine may have no network) to parse instructions or classify objects | model id, size, latency |
| Google DeepMind: Best Use of Gemini API | Gemini is used at runtime (unlikely: no network at evaluation) | — |

Can one technology challenge be linked by both of our submissions? [DA VERIFICARE with the Junction rules or organisers].

## Technology stack, by use [FILL]
| Use | Technology |
|---|---|
| Simulation | Isaac Sim via `aalto-sim:v1`, starter repo `aaltonomous-humanoid` |
| Perception | head RGB-D / wrist cameras → [FILL] |
| Planning / control | [FILL] (classical baseline? learned?) |
| Training data | Hugging Face datasets from the real robot? [FILL] |
| Compute | [FILL] (Verda RTX instance?) |
| Packaging | Docker linux/amd64, at most 40 GB, must fit 32 GB VRAM |

## Shared robot code (the only overlap with the other submission)
The organisers' runner on Windows (`tools/g1_windows_runner/`), the start-up path accepted by the safety filter (`g1/start_path.py`), and the Dex3 joint-limit clamping. Lessons from the real robot that apply to any policy (`docs/DELIVERY_G1.md`): the rest pose puts the wrists inside the counter keep-out, so the first move must go up; resting left fingers sit past the URDF limits, so every target must be clamped.
