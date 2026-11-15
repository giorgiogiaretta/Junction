# Judge scorecard — evidence, gaps and next actions

Evidence snapshot: `9ab91f9` (2026-11-15). Prepared for issue #169. Scores below are **editorial self-assessments**, not judge awards or measured performance; effort estimates are proposals, not promises. Owners follow `AGENTS.md`; time means focused time after the owner accepts the action. Challenge weights for Rokoko and NVIDIA were supplied in the task; Rokoko is also recorded in `docs/ORCH_BACKLOG.md`. No external rules were looked up.

## Claim discipline and entry status

Use `docs/ORCH_BACKLOG.md` section 1 as the wording floor: photo recognition is a small dataset result, grasp results are simulation, closure limits and break thresholds are toy/provisional, and hardware execution is unverified. Later dated results and executable code update the older audit; they do not remove those limits.

- **Rokoko: main entry. NVIDIA: intended entry.** These are the priorities in `docs/ORCH_BACKLOG.md` section 5.
- **Google Gemini: conditional entry; Gemma: reassess eligibility.** The old backlog declined Gemma absent local use. Later `docs/OBJECT_RECOGNITION_RESULTS.md` records PaliGemma on a team-controlled remote A100, while Gemma 4 evidence remains an API run. Neither proves entry acceptance.
- **CRACI / Entire: process candidates, currently skipped/unverified.** `docs/TOMORROW.md` says connection was skipped because CRACI required an organisation-owned repository matching its reserved organisation. Do not repeat the earlier “repo connected, every build scanned” wording in `docs/PITCH_AND_CHALLENGES_STORY.md` as a fact.

### Evidence reconciliation before presenting

| Older or optimistic wording | Evidence-backed wording now |
|---|---|
| No end-to-end simulation command | `robot/e2e_g1.py` now bridges a label (or online image recognition) to a capped/uncapped Dex3 simulation. Asset-dependent tests exist in `tests/test_e2e_g1.py`; code presence is not a successful run here. |
| Only one recognition run; answers unavailable | The later recognition report records a second Nemotron run; committed per-photo answers are in `docs/evidence/recognition/`. Original photos remain outside git. |
| Gemma 4 runs on our GPU | The recorded Gemma 4 result is through Google's API. The team GPU result is **PaliGemma 2**, a different model; see `docs/VERDA_GEMMA.md` correction. Remote self-hosting still needs connectivity. |
| Nemotron is the only fast model | Not supported: the later PaliGemma result has comparable reported latency. `docs/STORY_MODELS.md` is a pitch outline, not authority for exclusivity. |
| Two independent families are enforced | `ai/recognize.py` counts agreeing backend votes; `ai/object_profile.py` checks count and confidence, not model-family independence. Backend choice matters. |
| Endpoint failure costs one timeout | Code opens its in-memory breaker after **3 failures**, for **30 seconds** (`BREAK_AFTER`, `BREAK_FOR_S`); state resets across processes. |
| Can grasp is solved | The shared profile still marks can unsupported. Later V2 replay also reports failed can holding (`docs/G1_V2_RUN.md`). Separate posture experiments are not proof of a supported shared path. |
| Head-to-hand tracking demonstrated | Newer V2 code/replays exist, but operator/Coil conventions and physical camera coordinates remain unverified in `docs/G1_V2_RUN.md`. |

## Rokoko main

| Criterion | Weight | Our evidence (file / command) | Self-score /10 | Gap | Concrete next action — owner; estimate |
|---|---:|---|---:|---|---|
| Technical execution | 35% | `robot/e2e_g1.py`; `tests/test_e2e_g1.py`; `robot/g1_dex3.py`; `docs/G1_V2_RUN.md` | 6 | Integration exists, but assets/data are external and hardware unverified | Run capped/uncapped egg bridge with cached assets, save provenance and verdicts — Giorgio; 45 min |
| Originality | 25% | `ai/recognize.py`; `ai/object_profile.py`; `docs/OBJECT_RECOGNITION_RESULTS.md` | 7 | Fragile-first voting is implemented; no novelty survey or independent replication | Show same wrong egg label with/without shared cap; explain family-count limit — Tommaso/Claude; 30 min |
| Usefulness / impact | 25% | `docs/PHASE1_REAL_DATA.md`; `ml/grasp_assist.py` | 5 | Scripted simulation benefit; no user study or physical damage reduction | Collect marked-object grasp and failure examples with operator labels — Giorgio + Tommaso; 60 min |
| Live human-controlled robotics demo | 15% | `Rokoko/src/rgmp_client.py`; `g1/live_policy_v1.py`; `docs/G1_V2_RUN.md` | 3 | Replay/mock support is not a live physical demo | Rehearse live glove → simulation; record input source and output; physical test only through owner/staff procedure — Giorgio + Tommaso; 45 min |

Weighted editorial score: **5.55/10** = `(35*6 + 25*7 + 25*5 + 15*3)/100`. Do not turn this into a probability of winning.

## NVIDIA Best Use of Nemotron

| Criterion | Weight | Our evidence (file / command) | Self-score /10 | Gap | Concrete next action — owner; estimate |
|---|---:|---|---:|---|---|
| Meaningful use | 25% | `ai/eval_objects.py`; `ai/recognize.py`; `ai/object_profile.py` | 7 | Recognition affects closure decisions, but manual/offline alternatives exist | Demonstrate saved wrong-egg vote through the gate — Tommaso/Claude; 20 min |
| Technical execution | 25% | `tests/test_recognize.py`; `tests/test_picker_safety.py`; `ai/recognize.py` | 6 | Transport fakes test failure paths; live availability not verified here | Repeat endpoint failure rehearsal when authorised, record elapsed time and fallback — Tommaso/Claude; 30 min |
| Quality of output, including measured improvement | 25% | `docs/PROMPT_ITERATION.md`; `docs/evidence/recognition/nemotron_run2.json` | 6 | Prompt improvement used the evaluation images; no held-out claim | Freeze prompt and evaluate newly labelled photos; publish confusion and failed calls — Tommaso/Claude + Tommaso; 60 min |
| Creativity and differentiation | 25% | `ai/recognize.py`; `ai/object_profile.py`; `ai/crosscheck.py` | 7 | Risk-aware fusion is a useful design, not a proven safety property | Compare single model, shared cap, and vote on identical saved rows — Tommaso/Claude; 30 min |

Weighted editorial score: **6.50/10** = `(7+6+6+7)/4`.

**Form answers:**

- **Model:** reported as Nemotron 3.5 Super VL via Verda in `docs/OBJECT_RECOGNITION_RESULTS.md`. The exact deployed serving identifier must be confirmed; do not infer it from a marketing name.
- **What it does:** classifies a pre-grasp photo into an object category; the ensemble uses that category to select a closure cap. The older picker uses a `set_grasp_profile` tool call (`ai/profile_picker.py`); these are distinct interfaces.
- **Why essential:** it is the implemented fast NVIDIA recogniser in our demonstrated decision path. Its output matters to that path, but the system can fall back or use another model; it is not uniquely capable or the only fast option.
- **How output improved:** prompt A repeats were 47/50, 49/50, 49/50; B repeats were 49/50, 50/50, 50/50, including a failed call in each first repeat (`docs/PROMPT_ITERATION.md`). B was tuned after inspecting these photos. Shared caps and fragile-first voting improve downstream handling; they do not prove improved base-model generalisation.

## Google Gemma

**Official criteria and weights are unknown to us.** The following are planning assumptions with no official weighted total. PaliGemma eligibility and API versus self-hosted requirements need booth confirmation.

| Assumed criterion | Weight | Our evidence | Self-score /10 | Gap | Concrete next action — owner; estimate |
|---|---|---|---:|---|---|
| Meaningful Gemma-family use | Unknown | `ai/paligemma.py`; `docs/evidence/recognition/paligemma2_local.json`; `docs/VERDA_GEMMA.md` | 6 | Family eligibility unknown; API Gemma and self-hosted PaliGemma must stay distinct | Ask whether PaliGemma qualifies and retain written answer — Tommaso; 10 min |
| Technical integration | Unknown | `tools/paligemma_server.py`; `tests/test_paligemma_backend.py`; `ai/intent_router.py` | 6 | Remote tunnel required; JSON routing belongs to a different model path | Demonstrate normalisation and failure handling offline, then owner checks deployed model — Tommaso/Claude; 30 min |
| Measured quality | Unknown | `docs/OBJECT_RECOGNITION_RESULTS.md` | 5 | Same photos, several prompts, one egg→can error for PaliGemma | Evaluate frozen prompt on new hands/backgrounds — Tommaso/Claude + Tommaso; 60 min |
| Deployment benefit | Unknown | `docs/VERDA_GEMMA.md` correction | 4 | Self-hosted is not laptop-offline; no verified cost/privacy comparison | Record serving hardware, connectivity and resource use without secrets — Tommaso; 30 min |

Booth questions: Does PaliGemma qualify? Is API-hosted Gemma eligible? Is self-hosting required? Which model identifiers must the form contain? What are the official criteria/weights? Is an offline saved-answer demo acceptable? How should fine-tuning versus prompt work be described?

## Google Gemini

**Official criteria and weights are unknown to us.** Assumptions below are planning aids, not official scoring.

| Assumed criterion | Weight | Our evidence | Self-score /10 | Gap | Concrete next action — owner; estimate |
|---|---|---|---:|---|---|
| Meaningful Gemini use | Unknown | `ai/judge_gemini.py`; `docs/JUDGE_GEMINI.md` | 3 | Whole-episode judge exists; live judge evaluation unverified | Confirm accepted model and run a labelled episode when authorised — Tommaso/Claude; 30 min |
| Technical execution | Unknown | `tests/test_judge_gemini.py`; `ai/recognize.py` | 4 | Fake SDK coverage is not successful live inference | Preserve one successful and one failed-response example with provenance — Tommaso/Claude; 30 min |
| Output quality | Unknown | `docs/OBJECT_RECOGNITION_RESULTS.md`; `docs/JUDGE_RESULTS.md` | 2 | Gemini recognition only spot results/in-progress; Nemotron recall cannot be borrowed | Finish separate Gemini table including failures and labelled negative episodes — Tommaso/Claude + Tommaso; 60 min |
| Differentiation / impact | Unknown | `docs/JUDGE_GEMINI.md` | 3 | Async post-grasp assessment is plausible, not measured user benefit | Show one human-reviewed disagreement and explain uncertainty — Tommaso/Claude; 20 min |

Booth questions: Which models and APIs qualify? What are the official criteria/weights? Must a live Gemini call be shown? Does post-episode judging qualify independently of recognition? What evidence of improvement is required? Can failed/unclear results be included? What quota applies to the demo account (ask staff; do not assume old repo quota notes are current)?

## CRACI (process)

Official criteria/weights are not recorded in the reviewed repository. These are process assumptions; do not claim a completed entry.

| Assumed criterion | Weight | Our evidence | Self-score /10 | Gap | Concrete next action — owner; estimate |
|---|---|---|---:|---|---|
| Integration / scan evidence | Unknown | `docs/TOMORROW.md`; `.github/workflows/truth.yml` | 0 | Connection skipped; no CRACI scan artefact shown | Ask booth about organisation restriction and eligible evidence — Giorgio; 10 min |
| Traceable corrective process | Unknown | `AGENTS.md`; `tools/board`; Git history | 3 | Repo coordination exists but is not CRACI usage | Decide eligibility with staff; if feasible, authorised owner attaches actual scan and fix — Giorgio; 20 min initial triage |

## Entire (process)

Official criteria/weights and successful Entire integration are not established in the reviewed files.

| Assumed criterion | Weight | Our evidence | Self-score /10 | Gap | Concrete next action — owner; estimate |
|---|---|---|---:|---|---|
| Actual Entire usage | Unknown | `docs/ORCH_BACKLOG.md` §5; `docs/TOMORROW.md` | 0 | Process story is not a product usage record | Ask booth for eligibility and required session artefacts — Tommaso; 10 min |
| Human/agent traceability | Unknown | `AGENTS.md`; `tools/board`; issue #169 and its PR | 4 | Git/board provenance exists, no demonstrated Entire capture | Link issue→diff→tests→review; only claim Entire if an actual artefact exists — Tommaso; 20 min |

## Likely judge questions

Answers describe this snapshot. Evidence paths are relative to the repository root. “Reported” means a repository result, not rerun inference. No hardware or endpoint test was performed for this document.

### Rokoko — 20 questions

1. **What does the human control?** Finger closure and, in Coil-based V2, wrist motion; see `Rokoko/src/rgmp_client.py`, `g1/coil_chain.py`, `docs/G1_V2_RUN.md`.
2. **What does AI control?** Object interpretation and a proposed closure cap, not arbitrary joint actions; see `ai/recognize.py`, `ai/object_profile.py`.
3. **Why only simulation for the grasp claim?** No verified physical execution evidence is supplied; `docs/G1_V2_RUN.md` explicitly lists the physical robot as unverified.
4. **Is a replay a live human demo?** No. Recorded glove motion and synthetic motion must be labelled separately; see `docs/PHASE1_REAL_DATA.md`, `robot/pipeline.py`.
5. **Where is the end-to-end bridge?** `robot/e2e_g1.py`; `--label egg` bypasses recognition and tests the simulation path only.
6. **Does that bridge use the ensemble?** No: its image path calls `ai.eval_objects.recognize`, and its cap comes from `behaviour`; read `robot/e2e_g1.py` before claiming the full vote path.
7. **Can you grasp all recognised objects?** Not through the shared supported path: can is `supported:false` in `g1/object_profiles.json`.
8. **Why is the can problematic?** The shared profile records sideways expulsion; later V2 replay still reports unsuccessful can holding (`docs/G1_V2_RUN.md`).
9. **What improvement is measured?** The older five-finger simulation reports egg breaks 10/11→1/11 with real wrist paths and scripted closure (`docs/PHASE1_REAL_DATA.md`).
10. **Do real fingers reproduce that improvement?** Not in that experiment: the report records only 2/32 cube lifts for calibrated real grips and does not establish the cushion benefit on them.
11. **What is toy in the numbers?** Servo gains, contact/friction assumptions, object properties and break criteria are provisional; see `g1/sim/grasp_physics.py` and `robot/scene.py`.
12. **Are forces measured on hardware?** No. Force outputs in these reports are simulation-model values, not physical sensor readings (`docs/ORCH_BACKLOG.md` §1).
13. **Are closure values transferable as safe limits?** No. `g1/object_profiles.json` calls them provisional; hardware calibration remains required.
14. **How are the gloves mapped to Dex3?** Index/middle drive joint pairs; ring/little are ignored; thumb is coupled provisionally (`robot/g1_dex3.py`).
15. **Is thumb tracking verified?** No; `robot/g1_dex3.py` explicitly marks the thumb assumption unverified.
16. **What happens when vision fails?** The ensemble selects `other` and a conservative toy cap; the legacy picker returns `cup` (`ai/recognize.py`, `ai/profile_picker.py`). That is not universal physical safety.
17. **Is head-camera calibration real?** Do not generalise synthetic crop checks into live tracking; `ai/crop.py`, `tests/test_crop.py`, and the V2 unverified list state the boundary.
18. **Can the operator stop without a model?** Router stop words are matched locally (`ai/intent_router.py`); this software path is not proof of a physical emergency-stop system.
19. **What would you test next?** A marked object, labelled failures, and a live glove→simulation rehearsal, then staff-approved hardware checks (`docs/ORCH_BACKLOG.md`, `docs/G1_TEST_PLAN.md`).
20. **What is genuinely novel here?** Our contribution is the implementation of object-dependent closure with fragile-first disagreement handling; no priority claim is established (`ai/object_profile.py`, `ai/recognize.py`).

### NVIDIA — 20 questions

1. **Which model?** The result report names Nemotron 3.5 Super VL via Verda; exact serving identity still needs confirmation (`docs/OBJECT_RECOGNITION_RESULTS.md`, `ai/llm.py`).
2. **What is its input?** A pre-grasp image; evaluation preprocessing downsizes photos (`ai/eval_objects.py`).
3. **What is its output used for?** An object vote feeding closure policy, or a legacy profile tool call (`ai/recognize.py`, `ai/profile_picker.py`).
4. **Why is it meaningful rather than decorative?** Label errors can change the grip policy; the reported eggs mistaken for balls motivate the shared cap (`ai/object_profile.py`).
5. **Is it indispensable?** It is a meaningful implemented provider, not the sole possible provider; manual choice and alternative backends exist (`ai/pick_profile.py`, `ai/recognize.py`).
6. **How accurate is it?** Saved second-run answers score 48/50 on these photos only (`docs/evidence/recognition/nemotron_run2.json`).
7. **What exactly failed?** `egg-012` and `egg-014` became `stress_ball` in that run (`docs/OBJECT_RECOGNITION_RESULTS.md`).
8. **Why not trust confidence?** Both incorrect eggs score 0.90, also seen on correct answers; no separating threshold was demonstrated (same report).
9. **What does two-key actually enforce?** Count plus mean confidence, with fragile-first selection; it does not enforce distinct families (`ai/recognize.py`, `ai/object_profile.py`).
10. **Does agreement prove correctness?** No; `ai/crosscheck.py` reports agreement, not ground truth on unlabelled photos.
11. **What does the saved cross-check show?** 69/77 agree overall, 47/50 labelled agree, three single-model errors flagged (`python3 -m ai.crosscheck docs/evidence/recognition/nemotron_run2.json docs/evidence/recognition/gemma4_api.json`).
12. **What changed in your prompt?** Visual cues about pale oval eggs, orange balls and cans were added (`docs/PROMPT_ITERATION.md`).
13. **What improved numerically?** A repeats: 47,49,49 of 50; B: 49,50,50, with first-repeat failed calls; same-photo tuning makes this optimistic (same report).
14. **Is that held-out validation?** No; the prompt was revised using errors from the same photos (`docs/PROMPT_ITERATION.md`).
15. **What is the latency claim?** Second run reports median HTTP latency 0.22 s, not complete camera-to-hand latency (`docs/OBJECT_RECOGNITION_RESULTS.md`).
16. **What if the endpoint is down?** Failed votes are excluded; no successful vote yields conservative fallback; breaker opens after three failures (`ai/recognize.py`).
17. **Does the timeout kill every request thread?** No: collection returns without waiting, but running futures are not forcibly stopped (`collect`, `shutdown(wait=False)` in `ai/recognize.py`).
18. **Can a judge reproduce recognition offline?** They can recompute saved-answer scores, not rerun model inference without images and a service (`docs/evidence/recognition/README.md`).
19. **Did the episode judge improve too?** Reported positive recall went 5/32→22/32, but that run lacked the timeline and had no negatives; do not confuse it with recognition (`docs/JUDGE_RESULTS.md`).
20. **What evidence would most strengthen this entry?** A frozen prompt on a new labelled set plus a logged failure rehearsal; this addresses the stated caveats in `docs/PROMPT_ITERATION.md` and `docs/OBJECT_RECOGNITION_RESULTS.md`.

### Google Gemma — 20 questions

1. **Which Gemma models were used?** Gemma 4 via API and PaliGemma 2 on a team GPU, with separate evidence files (`docs/evidence/recognition/README.md`).
2. **Why Gemma through an API at first?** It provided a second recogniser before the self-hosted setup; later deployment notes motivate control of quota and latency (`docs/VERDA_GEMMA.md`).
3. **Did Gemma 4 actually run locally?** Not established by the committed result: `gemma4_api.json` is explicitly API evidence.
4. **What ran on your GPU?** Reported PaliGemma 2 3B on a Verda A100 via SSH tunnel (`docs/OBJECT_RECOGNITION_RESULTS.md`).
5. **Is that offline on this laptop?** No. Remote self-hosted inference still depends on the remote GPU and tunnel (`ai/paligemma.py`).
6. **Does PaliGemma output robot actions?** No; it answers an object question, then deterministic code maps the label (`ai/paligemma.py`, `ai/object_profile.py`).
7. **What did API Gemma score?** 49/50, including 20/20 eggs, on the saved set (`docs/evidence/recognition/gemma4_api.json`).
8. **What did PaliGemma score?** 49/50 for the three-option prompt; one egg became can (`docs/OBJECT_RECOGNITION_RESULTS.md`).
9. **What prompt failed?** Binary fragile/rigid returned fragile on 48/50 and scored only 22/50 binary correctness (same report).
10. **Why is that failure important?** Conservative wording can hide useless discrimination; we report the failed prompt, not just the best one (same report).
11. **Was the best prompt selected independently?** Three prompts were tried on the same photos, so the best result is optimistic even if each prompt preceded its run (same report).
12. **Does PaliGemma provide confidence?** No; its adapter returns `confidence: None` (`ai/paligemma.py`).
13. **How can a no-confidence vote be used?** It counts toward agreement; confidence averages available values, and an egg vote with unknown confidence can veto (`ai/recognize.py`).
14. **What happens if its server is missing?** The backend returns `ok:False`; the ensemble ignores that failed vote (`ai/paligemma.py`, `tests/test_paligemma_backend.py`).
15. **Can PaliGemma replace the JSON router?** Not with this adapter; it is a short-answer model path, whereas the router expects validated JSON (`docs/VERDA_GEMMA.md`, `ai/intent_router.py`).
16. **What does the router do?** Maps text to change-profile, stop or none; invalid responses fall back to none (`ai/intent_router.py`).
17. **Can “squeeze harder” override an egg?** The router's gate refuses firm mode except for a current stress-ball label; a mistaken current label remains a risk (`apply_intent` in `ai/intent_router.py`).
18. **Can you claim all data stays on the laptop?** No. API calls send images to providers; self-hosting is on remote infrastructure (`ai/eval_objects.py`, `docs/VERDA_GEMMA.md`).
19. **Does this qualify for the Gemma prize?** Unknown; ask whether PaliGemma-family use and API Gemma are eligible. The older backlog's “no” predates the new evidence (`docs/ORCH_BACKLOG.md`, recognition report).
20. **What would you improve next?** New held-out photos, deployed-model provenance and explicit backend selection; those address the report's dataset and deployment limits.

### Google Gemini — 20 questions

1. **What is Gemini's intended role?** Backup recognition and post-episode judging (`ai/recognize.py`, `ai/judge_gemini.py`).
2. **Is it in the motor loop?** The intended judge reads completed episodes; it does not generate joint commands (`docs/JUDGE_GEMINI.md`).
3. **Which model identifier is proven?** No single identifier is verified for every path; executable `DEFAULT_MODEL` is `gemini-3.1-flash-lite`, older judge prose differs, and recognition reports another Flash generation (`ai/judge_gemini.py`, `docs/JUDGE_GEMINI.md`, recognition report).
4. **Do you have a complete Gemini photo benchmark?** Not in the reviewed results: the table says in progress and gives a 5/5 spot test only (`docs/OBJECT_RECOGNITION_RESULTS.md`).
5. **Can you substitute Gemma's score?** No. Separate models, backends and result provenance (`docs/evidence/recognition/README.md`).
6. **Was there a failed Gemini run?** The report records 77/77 failures and attributes them to venue network loss; this is reported history, not remeasured here (`docs/OBJECT_RECOGNITION_RESULTS.md`).
7. **What does the episode judge read?** Closure and wrist samples from a whole episode, optionally head-relative hand data (`ai/judge_gemini.py`, `docs/JUDGE_GEMINI.md`).
8. **Does it watch video?** The documented judge consumes compact episode JSON; do not describe that as watching the full video (`docs/JUDGE_GEMINI.md`).
9. **What is its ground truth?** Existing labels describe object-not-dropped positives; labelled failures are missing (`docs/JUDGE_GEMINI.md`).
10. **Can you report judge accuracy?** No, neither class coverage nor a live Gemini confusion table is established (same document).
11. **Does Nemotron agreement establish accuracy?** No; `ai/crosscheck.py` and `docs/JUDGE_GEMINI.md` distinguish agreement from truth.
12. **What happens on invalid JSON?** Judge result becomes unclear/non-evaluated after error handling (`ai/judge_gemini.py`).
13. **Does printed False always mean a failed grasp?** No: the judge documentation says an unclear result can print False with NON VALUTATO; inspect status (`docs/JUDGE_GEMINI.md`).
14. **What has been tested offline?** Fake-client SDK and judge logic checks (`tests/test_judge_gemini.py`), not live service availability.
15. **Can recognition fall back when Gemini fails?** The ensemble excludes failed votes and keeps conservative fallback when all fail (`ai/recognize.py`).
16. **Why use a slower model after the take?** Asynchronous assessment need not block control; this is the design rationale, not measured user impact (`docs/STORY_MODELS.md`, `docs/JUDGE_GEMINI.md`).
17. **Are quota claims current?** Not verified here; deployment docs contain historical assumptions, so ask the booth (`docs/VERDA_GEMMA.md`).
18. **What are the official judging weights?** Unknown in the supplied evidence; the table above is explicitly assumed (`docs/ORCH_BACKLOG.md` §5 records priority, not Google criteria).
19. **What demonstration is defensible today?** Show code and fake-client tests, and label any saved spot results as such (`tests/test_judge_gemini.py`, recognition report).
20. **What blocks a stronger entry?** A completed live, labelled evaluation with negative examples and model identity; see `docs/JUDGE_GEMINI.md` unverified section.

### CRACI — 20 questions

1. **Is CRACI connected?** Not established; latest reviewed plan says skipped (`docs/TOMORROW.md`).
2. **Why skipped?** It records an app-owner/reserved-organisation mismatch (same file).
3. **Is a green workflow a CRACI scan?** No; `truth.yml` runs pytest, not a demonstrated CRACI scan (`.github/workflows/truth.yml`).
4. **Where is the scan report?** No report is supplied in the cited process evidence; do not invent one (`docs/TOMORROW.md`).
5. **Why consider the challenge?** The backlog allowed a short conditional process integration (`docs/ORCH_BACKLOG.md` §5).
6. **Was entry confirmed?** No confirmation is recorded there; eligibility remains a booth question (same section).
7. **What are official criteria?** Unknown in reviewed repo documents; planning assumptions are not official weights (`docs/PLAN.md`, `docs/ORCH_BACKLOG.md`).
8. **Who owns the decision?** Giorgio leads; workflow changes need the authorisation noted in the backlog (`AGENTS.md`, `docs/ORCH_BACKLOG.md`).
9. **Will this PR change CI?** No; issue #169 claims only the scorecard and tour.
10. **What process is actually implemented?** Issues, owned paths, board coordination, small commits and PR review (`AGENTS.md`, `tools/board`).
11. **Does process imply product use?** No; GitHub coordination is evidence of coordination only (`AGENTS.md`).
12. **What does CI test?** Explicit selected test files, not automatically all tests (`.github/workflows/truth.yml`).
13. **Does CI green imply hardware safety?** No: the simulation and hardware limitations remain (`docs/ORCH_BACKLOG.md` §1).
14. **Are skipped tests successful tests?** No; asset/data-dependent tests skip when inputs are missing (`tests/test_e2e_g1.py`, `tests/test_real_takes.py`).
15. **Is the historical 89-test result current?** It belongs to the older audit; use a timestamped current command result instead (`docs/ORCH_BACKLOG.md`).
16. **How do you trace a fix?** Issue→branch→commit→PR→test output, per `AGENTS.md` and issue #169.
17. **Can you claim every build is scanned?** No; that earlier story wording conflicts with the skipped integration note (`docs/PITCH_AND_CHALLENGES_STORY.md`, `docs/TOMORROW.md`).
18. **What would establish CRACI use?** An actual eligible connection and scan artefact, not another paragraph; this follows the documented integration gap (`docs/TOMORROW.md`).
19. **What if setup takes too long?** Keep it off the critical path; backlog gives the conditional short-time budget (`docs/ORCH_BACKLOG.md` §5).
20. **What will you ask staff?** Eligibility of this repository, organisation requirements, required scan artefacts and judging criteria; these resolve the recorded blocker (`docs/TOMORROW.md`).

### Entire — 20 questions

1. **Is Entire demonstrated?** No successful integration artefact is established by reviewed process docs (`docs/ORCH_BACKLOG.md`, `docs/TOMORROW.md`).
2. **Is it a confirmed entry?** No; it remains conditional in the backlog (`docs/ORCH_BACKLOG.md` §5).
3. **Why is it in this scorecard?** To track a requested process candidate without claiming use; same backlog.
4. **What are its official criteria?** Unknown from supplied evidence; no official score total is computed here.
5. **Can board logs stand in for Entire sessions?** No. `tools/board` is a GitHub-issue workflow.
6. **What human/AI collaboration can you prove?** Ownership and explicit board/issue/PR workflow, not an Entire capture (`AGENTS.md`, issue #169).
7. **How are decisions attributed?** Posts start with a human/agent signature (`AGENTS.md` §1).
8. **How are overlapping edits avoided?** Exclusive folder ownership and owner requests (`AGENTS.md` §4–5).
9. **Does an agent merge this PR?** No; Codex-specific rules leave it unmerged for review (`AGENTS.md`, issue #169 scope).
10. **Are generated results accepted blindly?** Rules require review before commit (`AGENTS.md` §5–8).
11. **Was a delegate used here?** No delegate tool was available in this session; the author read the code and reviewed these two files directly.
12. **How do you distinguish plans from results?** Cite executable code or dated reports; proposed owner/time actions are explicitly estimates (`docs/ORCH_BACKLOG.md` distinguishes acceptance commands from completed work).
13. **How do you avoid inflated model claims?** Keep dataset scope, prompt tuning and failed calls beside the score (`docs/PROMPT_ITERATION.md`).
14. **What is reproducible from the clone?** Saved-answer comparisons and available offline tests; images, robot and endpoint are separate prerequisites (`docs/evidence/recognition/README.md`).
15. **Are hidden local datasets committed?** No data additions are part of this issue; photo evidence lists filenames/answers, not photos (`docs/evidence/recognition/README.md`, issue #169).
16. **Is there a complete assistant transcript here?** Not established; a signed board post is not a full transcript (`tools/board`, `AGENTS.md`).
17. **Is the CRACI blocker automatically an Entire blocker?** No. The organisation error is specifically CRACI; Entire status needs separate confirmation (`docs/TOMORROW.md`).
18. **What evidence would justify an Entire claim?** A real accepted session artefact linked to the reviewed change; current process docs do not supply that.
19. **Who should resolve eligibility?** Tommaso can ask the booth and bring requirements to Giorgio; ownership and leadership follow `AGENTS.md`.
20. **What is the honest process pitch now?** A coordinated human/agent GitHub workflow with review and test evidence; no unverified product integration (`AGENTS.md`, `.github/workflows/truth.yml`).
