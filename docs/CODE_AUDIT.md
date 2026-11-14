# Read-only code audit — real-robot boundaries first

Issue #179. Author: Tommaso's Codex-Audit. Snapshot: `6d2e6abf34308e7a587c44db951fa3e571a6ab74` (merged main, checked with `git log -1` and `gh api repos/giorgiogiaretta/Junction/branches/main --jq .commit.sha`). Line references below belong to this snapshot. Only this document is changed; fixes are proposals for the owners. Final review detected a newer main; see F12 for the verified resolution. The branch retains the audited snapshot: the task permits network only for git push, gh and tools/board, so no git fetch was performed.

Read first: `AGENTS.md`, `README.md`, `docs/ORCH_BACKLOG.md` (especially section 1), `docs/SCORECARD.md`, `docs/CODE_TOUR.md`. The current role/worktree/file assignment overrides the older generic Codex folder rule. Issue creation records the claim; the requested single board post is reserved for the completed PR. No delegate tool is available; review was performed directly. Network use was limited to GitHub/board operations; no inference, downloads or hardware connections were made. Tests include local loopback fixtures.

**This is not a hardware clearance.** Severity describes the potential consequence and missing boundary, not an observed incident. “Confirmed” means source reasoning or the isolated offline probe reproduced the software behaviour. Physical consequences and external-runner mitigation remain unverified. No critical incident is established. All closure values, object thresholds and simulation results remain toy/provisional, not physical-force measurements.

Real-robot history is only as reported in `tools/g1_windows_runner/README.md`: glove-driven arms/hands were run, while the camera computer was unavailable in that documented session. `docs/G1_GUIDE.md` and `docs/G1_LIVE.md` retain calibration, thumb and physical-grasp limitations. Comments claiming later staff approval are not independently verified here. The organisers' actual installed runner and Windows deployment are outside this audit snapshot.

## Hardware findings

### F01 — high — Unset or NaN closure limit permits full range (confirmed)

**Source:** `robot/g1_dex3.py:19-26`, called by `g1/arms_simple.py:108`, `g1/arms_glove.py:190`, `g1/live_policy_v1.py:122`, `g1/live_policy_v2.py:122`; `start_g1.ps1:17`.

**What happens / reproduction:** With an empty environment, `G1Dex3Retargeter().max_closure` is `1.0`. Passing `max_closure=float('nan')` also produces `1.0` through Python's ordered `min/max`. The launcher defaults to `0.6`, not the initial `0.1` procedure in `docs/G1_GUIDE.md:38`. Explicit object caps may reduce the requested closure, but do not make the hardware scale fail closed. These are closure fractions, not force values.

**Suggested fix:** Require an explicit finite, bounded hardware limit before serving; use the owner-approved initial limit and a separate deliberate escalation. Reject NaN/infinity instead of silently saturating. Preserve explicit full-range simulation use separately.

### F02 — high — Lost glove stream remains a live command (confirmed)

**Source:** `g1/arms_simple.py:57-70,115-133`; `g1/arms_glove.py:57-70,220-229`; `g1/live_policy_v1.py:78-92,279-287`; `g1/live_policy_v2.py:87-103,315-332`; `g1/coil_chain.py:197-211`.

**What happens / reproduction:** Readers retain the last sample indefinitely, without receipt-age checks. Give a closed sample, then make `recv` raise `BlockingIOError`: repeated reads still return the closed sample. V1 can advance timed descend/grasp/lift states after input loss. V2 continues feeding retained poses to filters/assist and can count repeated stale samples as “still” for anchoring. Valid policy replies continue, so a watchdog for missing policy replies is not an input-freshness watchdog. V1 rejects invalid new fingers but retains old fingers.

**Suggested fix:** Track monotonic receipt time and sequence per hand; invalidate stale data, hold via a defined safe-stop policy, and require fresh neutral input to resume. Reset cached input across episodes. Do not automatically open a held object as the assumed safe response.

### F03 — high — Invalid glove/quaternion data can close fingers or break control (confirmed)

**Source:** `g1/finger_map.py:16-23,27-30`; `g1/arms_simple.py:63-69`; `g1/arms_glove.py:63-69`; `g1/live_policy_v2.py:91-103,315-332`; `g1/coil_chain.py:88-98,122,207-211`.

**What happens / reproduction:** `closures([NaN]*5, .6)` returns `[1,1,1,0,0]`; direct retargeting of NaN also requests the full index target (`1.5508` radians in the current limits file). The inherited standard mapper's NaN handling is bypassed by `DirectRetargeter.targets`. A zero quaternion produces four NaNs in `QuatEuro`; V2 checks position finiteness but not quaternion norm/shape or finger finiteness. A malformed JSON datagram raises uncaught `JSONDecodeError` in the simple/glove readers and V2; short vectors can raise indexing errors. This proves bad requests/errors, not that the runner executes nonfinite joints.

**Suggested fix:** Validate the entire packet before caching: expected dimensions, finite closures/positions, nonzero finite quaternion, explicit range handling. Reject malformed packets without retaining stale authority; apply F02. Validate finite output vectors before every return.

### F04 — high — Fast mode removes table protection and weakens more than its label suggests (confirmed)

**Source:** `start_g1.ps1:15-22`; `tools/g1_windows_runner/winshim/sitecustomize.py:5-17`; `g1/live_policy_v2.py:33-45,126-127,283-286`; `g1/sim/teleop_sim.py:57-65`.

**What happens / reasoning:** `G1_FAST=1` removes counter keep-out from newly constructed runner configurations, defaults runner arm speed to `2.0`, and allows an unvalidated `G1_FAST_ARM_VEL`. V2 increases its joint speed to `1.8`, lowers its floor by `0.25` relative to `D.KEEP['z']`, and retains only `self...` reasons from `T.unsafe`: policy-side box violations are discarded too. The runner box may still protect that boundary. `_fast.from_yaml = _Orig.from_yaml` also leaves a construction route outside the wrapper; whether the installed runner takes that route is **UNCONFIRMED**.

**Suggested fix:** Preserve a calibrated table volume and explicit box checks; version and validate one effective safety configuration across policy and runner. Reject nonfinite/out-of-range overrides; verify the actual runner configuration before motion. Do not infer approval for a changed setup from a source comment.

### F05 — high — Workspace-check failure permits continued motion (confirmed)

**Source:** `g1/live_policy_v1.py:33-40,299,333`; `g1/live_policy_v2.py:38-45,149-154,169-173`.

**What happens / reasoning:** Any exception while constructing `WorkspaceChecker` becomes `WS=None`. V1 then omits its organiser-compatible escape/check. V2 returns a joint-clamped candidate without workspace validation and chooses a direct startup path `[self.rest_q]`. Other geometry checks do not establish equivalent coverage, particularly during startup and Fast mode. The downstream runner may reject these commands; its installed behaviour is not verified here.

**Suggested fix:** Refuse hardware startup if safety dependencies/calibration are unavailable. Keep degraded operation behind an explicit simulation-only path. Test missing URDF, malformed config and failed checker construction.

### F06 — high — V2 reset retains exhausted startup paths; background plans lack episode isolation (confirmed)

**Source:** `g1/live_policy_v2.py:140-147,169-183`; `g1/arms_glove.py:133-145,188,210-213`.

**What happens / reproduction:** V2 reset clears `started` but not `wps`, `wp_i` or `planning`. After finishing a path, `wp_i == len(wps)`; reset followed by startup accesses `self.wps[self.wp_i]` and raises `IndexError`. An isolated call of the real reset method retained a one-element path with index one. In both policies a planning thread can publish `wps` after reset without checking an episode identifier, unlike the perception workers.

**Suggested fix:** Clear all startup state, cancel/discard prior-generation planner results, and publish immutable plan results under the episode lock. Test reset during planning, after success, and after failure.

### F07 — high — V1 workspace scaling leaves IK state ahead of the command (confirmed)

**Source:** `g1/live_policy_v1.py:306-343`; compare `g1/live_policy_v2.py:343-344`.

**What happens / reasoning:** IK first updates `self.kin.a.q` to a candidate. When workspace bisection gives a fractional step, only `arm_target` and `last_cmd` become the accepted fraction; the IK model stays at the candidate. The conditional at line 342 only runs for zero fraction and restores `prev`, which in the escape branch was captured after the escape update. Thus the next iteration's geometric checks and solve can start from a pose different from the emitted command. V2 explicitly synchronises the model after scaling. Resulting repeated blocks or unsafe proposals are possible; a physical collision is **UNCONFIRMED**.

**Suggested fix:** After every clamp, bisection, rejection or dry-run branch, synchronise the IK model to the authoritative accepted command. Add a fractional-bisection regression that checks this equality each tick.

### F08 — high — Startup does not run the normal self-collision gate (confirmed omission)

**Source:** `g1/live_policy_v2.py:162-193,310,283-287`; `g1/live_policy_v1.py:299-307`; `g1/start_path.py:18-24,55-56,73-84`; `g1/arms_glove.py:195-214`.

**What happens / reasoning:** V2 returns from `_startup` before the normal `_unsafe`/`solve_arm` path. V1's `escape_up` bypasses `_geom_violations`, where self-collision is tested. The planner only queries `WS.violation`; it never invokes the explicit self-collision callback. `g1/sim/teleop_sim.py:64` describes that collision check as outside the organisers' filter. Hence “self-collision kept” does not establish coverage of startup. An actually colliding startup trajectory is **UNCONFIRMED**; the external WorkspaceChecker implementation was not available as tracked code here.

**Suggested fix:** Apply a common joint, speed, workspace and self-collision validator to startup, escape and normal motion, including sampled segments. Fail closed on missing coverage; validate supported measured start poses offline.

### F09 — high — Dry mode is not a reliable stationary, filter-valid rehearsal (confirmed)

**Source:** `g1/live_policy_v1.py:246-247,268,359`; `g1/live_policy_v2.py:189-193,345-348`; `tools/g1_windows_runner/README.md` (“Dita sinistre a riposo”).

**What happens / reasoning:** V1 returns its original measured pose in dry mode, then clips it in `act`, so out-of-range measurements can become a different target despite the “robot does not move” instruction in `docs/G1_GUIDE.md:37`. V2 does the reverse: after clamping the normal hand command, dry branches restore raw measured arms/hands without final validation. The README explicitly reports measured left fingers outside the filter bounds. Therefore V2 dry mode can submit out-of-filter targets; V1 can request corrective motion. No physical dry run was performed.

**Suggested fix:** Separate compute-only preview from actuator-enabled serving. If a hold-command rehearsal is required, define an owner-approved validated hold initialisation and report any correction; test out-of-range measured start poses and slew effects.

### F10 — high — Launcher can switch a running session without a verified stop/identity handshake (confirmed missing interlock)

**Source:** `start_g1.ps1:42-46,66-77`; `tools/g1_windows_runner/winshim/run_real.ps1:21-25`.

**What happens / reasoning:** The launcher force-kills processes matching policy/input names, but does not stop or wait for an already running `aaltonomous.deploy.runner`. Readiness means only that port 8000 accepts TCP; it does not verify the new policy identity, closure limit, glove freshness or safety mode. Starting the script during an existing run can therefore terminate its controller and start another runner without coordinating the old runner. The old runner's reconnect/exclusive-DDS behaviour is **UNCONFIRMED**; no duplicate-run experiment was attempted.

**Suggested fix:** Use a single-session lock, stop acknowledgement and process handles owned by the launcher. Verify policy metadata and effective safety settings before enabling the runner; perform deterministic cleanup on failure/Ctrl+C.

## Model-facing and input-boundary findings

### F11 — high — Wrong-provider credential fallback (confirmed source path; no credentials read)

**Source:** `ai/eval_objects.py:22-24`; `ai/llm.py:30-35,45,54`; `ai/intent_router.py:38-41`.

**What happens / reasoning:** With Google credentials absent, `make_client('gemini')` passes `api_key=None` with an explicit Google URL. `ChatClient` independently falls back to the Verda/NVIDIA/general credential, then sends it to that URL. The URL and credential are not bound as a pair. The router also changes a constructed client's URL without replacing its credential. This contradicts `ai/eval_objects.py:4` (“Each key is only sent to its own endpoint”). Actual disclosure is **UNCONFIRMED**; no real key, environment secret or endpoint was accessed.

**Suggested fix:** Distinguish “no explicit provider credential” from generic autodetection; fail closed for missing provider-specific credentials. Bind credential scope to approved origin and require a separately scoped local credential on URL overrides.

### F12 — high — Duplicate recogniser entries unlock the nominal two-vote cap (confirmed in audited snapshot; resolved on newer main)

**Source:** `ai/recognize.py:71-85,94-111,129-131`; `ai/object_profile.py:73-81`.

**What happens / reproduction:** Use `backends=['same','same']` with one fake registry function returning `stress_ball`, confidence `.99`, `ok=True`. `recognise` returns `agree=2`, `cap=1.0`: identical backend names are submitted twice and counted twice. Distinct names also do not prove independent model families. An image-induced wrong label can therefore gain more closure authority than the claimed independent confirmation boundary. Successful visual prompt injection against an actual model is **UNCONFIRMED**.

**New-main follow-up:** During final review, `gh api` showed main advanced to `3e7190831530440e3d351865e4d4e2cfd944be93`. Its only changed paths relative to the audited snapshot are `ai/recognize.py` and `tests/test_recognize.py`. The new `FAMILY` mapping and distinct-family count resolve this duplicate-vote finding for the built-in names. Fetching that file via `gh api` into a temporary file and rerunning the same fake probe returned `agree=1, cap=0.7`. F12 is historical, not an outstanding defect on that newer main. The full-suite result below belongs to the original snapshot. Model misclassification and provenance of custom registry aliases remain separate limitations.

**Suggested fix:** Deduplicate authenticated backend identities and enforce the intended family/provenance policy before granting elevated closure. Treat image text and generated labels as untrusted; never allow response fields to claim manual authority.

### F13 — medium — Malformed confidence is either fatal or sufficient to elevate the cap (confirmed)

**Source:** `ai/eval_objects.py:35-39`; `ai/recognize.py:94-106`; `ai/object_profile.py:79,119`; `ai/perceive.py:121`.

**What happens / reproduction:** Recognition passes `r.get('confidence')` through unvalidated. `decide` with a successful egg vote whose confidence is `'high'` raises `TypeError`; `cap_for_votes('stress_ball', float('inf'), 2)` returns `1.0`. Agreement conversion can also throw on malformed values. Catching transport failure does not validate successful JSON. The current model may usually emit valid values; that is not an enforced invariant.

**Suggested fix:** Validate canonical label, strict boolean success, finite confidence in `[0,1]`, and bounded integer agreement at the boundary. Derive agreement from validated unique votes rather than trusting a supplied count. Malformed responses should yield conservative failure.

### F14 — high — Spoken model output is treated as manual full-closure authority (confirmed helper behaviour; live integration unconfirmed)

**Source:** `ai/intent_router.py:45-54,62-72`; `ai/object_profile.py:73-81`.

**What happens / reproduction:** `apply_intent({'action':'change_profile','target_profile':'rigid','via':'model'}, 'stress_ball')` returns cap `1.0`, without checking object confidence or provenance, or separately confirming an operator override. If a single recogniser mislabels a fragile item as a ball, a model-routed phrase can bypass its conservative shared cap. Schema validation blocks arbitrary actions, but cannot establish genuine intent; adversarial speech can ask for a valid rigid action. Even direct callers with another target value reach the rigid branch because `apply_intent` does not revalidate it. The searched production robot/policy paths do not call this helper; this is not evidence of a deployed voice-to-robot exploit.

**Suggested fix:** Preserve trusted object provenance and explicit override confirmation; model output alone must not set `manual=True`. Revalidate at application time. Implement a latched stop independently of delayed model callbacks; a returned numeric cap is not an emergency-stop implementation.

### F15 — medium — Advisor can raise the fallback cap, and NaN confidence is treated as certain (confirmed)

**Source:** `ai/advisor.py:19-40,43-54`.

**What happens / reproduction:** `clean({'object':'object','confidence':NaN,'fragility':0})` followed by `advice_cap` returns cap `.70` with `needs_operator_confirm=False`. `_num` maps NaN to its upper bound. More generally the model can move a result from conservative `.68` to shared `.70`, contradicting “only ever LOWER” at lines 5-6; the helper has no current cap argument and could exceed a smaller current profile. Full closure is still blocked by this helper. No production hardware caller was found by `rg -n 'advice_cap|advise\(' demo robot g1 ai`.

**Suggested fix:** Reject nonfinite numbers and wrong scalar types; compute `min(current_cap, proposed_cap)` and retain confirmation on uncertainty. Keep experimental advice out of actuator authority until that contract exists.

### F16 — medium — Errors can retain sensitive transport text (confirmed echo mechanism; actual leak unconfirmed)

**Source:** `ai/llm.py:56-63`; `ai/eval_objects.py:38-39`; `ai/recognize.py:122-123`; `ai/judge_gemini.py:142-148,164-168`.

**What happens / reproduction:** A fake 401 response body containing the inert text `NONSECRET_MARKER` produces an `LLMError` containing it. The recogniser can return and log that error. Network exception text is likewise retained. Gemini sanitises general SDK exceptions, but the earlier `ValueError/KeyError/TypeError/AttributeError` catch includes raw text from errors thrown by the SDK call, not only parsing. Provider error bodies can echo request material. No actual credential disclosure was observed or sought.

**Suggested fix:** Return structured status/type codes only; redact before any log/report boundary. Separate transport and parse exception handling. Exercise redaction with inert markers, never live keys.

### F17 — medium — Timeouts do not bound worker lifetime or service resource use (confirmed)

**Source:** `ai/recognize.py:74-84`; `ai/perceive.py:113-120`; `ai/judge_gemini.py:96-107,135-153`; `tools/paligemma_server.py:41-45,49-76`.

**What happens / reasoning:** Executors return on their collection deadline but cannot cancel already-running threads. Repeated recognitions/crops can leave work behind. The Gemini client/config sets no explicit application deadline; retries only begin after a call returns. PaliGemma uses an unbounded threaded server, reads arbitrary `Content-Length`, and queues generation behind a lock with no queue deadline. Token output is upper-bounded, but request/image size, queue length and execution time are not. With `--host 0.0.0.0` and no `LOCAL_KEY`, authentication is disabled; default loopback binding limits exposure. No live stress test was run.

**Suggested fix:** Use bounded shared executors/queues, transport deadlines and total request budgets; expire queued work. Validate body/image sizes and token lower bounds. Require authentication for non-loopback binds. Do not call the collection deadline a hard kill of inference.

### F18 — high — Location can be marked usable with a nonfinite position (confirmed helper behaviour)

**Source:** `ai/locate.py:125-138,148-177`; `ai/perceive.py:131-137`; `g1/live_policy_v1.py:179-196`; `g1/live_policy_v2.py:262-265`.

**What happens / reproduction:** On an interior egg mask with uniform positive depth and `pixel_to_pelvis=lambda *args:[0,0,0]`, `locate` normalises a zero ray, returns `[NaN,NaN,NaN]` and `depth_ok=True` when no table gate is supplied. `perceive`'s usable expression checks non-None, not finiteness. V1's `distance > gate` test is false for NaN, so it is not a substitute for validation. V2's camera test is more restrictive when CLI coordinates are present. Reachability through the current calibrated end-to-end perception path is **UNCONFIRMED**; the public location contract violation was reproduced.

**Suggested fix:** Reject invalid projection/ray/position/axis results before declaring `depth_ok`; validate shape, finite coordinates and allowed workspace again in policy consumers. Fail closed on invalid calibration.

### F19 — medium — Profile override JSON is insufficiently validated (confirmed source path)

**Source:** `ai/object_profile.py:15-29,42-65,73-81`.

**What happens / reasoning:** Only `max_closure` being an `int/float` is checked; NaN/infinity/bools pass that test. Other fields are copied verbatim. A top-level JSON list fails at `.get`; malformed hold/break fields can fail during import-time robust-cap computation or produce nonsensical arithmetic. This is a local configuration boundary, not a demonstrated photo/spoken-input write path. The committed profile is not alleged to contain these malformed values.

**Suggested fix:** Validate the whole schema and all numeric bands atomically before replacing defaults; reject nonfinite values, wrong types and inconsistent hold/break bounds. Never broaden a cap on configuration failure.

## Tests and contradictory claims

### F20 — high — Hardware filter “tests” report failure without failing their command (confirmed)

**Source:** `tools/g1_windows_runner/arms_test.py:24-34`, `arms_glove_test.py:24-41`, `v1_filter_test.py:25-39`, `v2_filter_test.py:16-30`, `check_shim.py:17-26` (all under the same folder).

**What happens / reasoning:** These scripts print clip counts, abort states, startup progress or numerical shim error but contain no assertions or nonzero exit on a failed criterion. V1/V2 even break on abort and then finish printing normally. A completed command can therefore be green after a failed safety scenario. They can still fail from exceptions; “cannot fail” here means the intended numerical/safety acceptance criterion does not affect exit status. They are outside the requested `pytest tests` directory and are not invoked in `.github/workflows/truth.yml:10-13`.

**Suggested fix:** Convert acceptance criteria to explicit failures and assert meaningful progress so “no motion” cannot pass as “no clips.” Add reset, stale/malformed input, Fast/configuration and startup cases against a pinned organiser runner; keep these offline.

### F21 — medium — Episode coverage silently passes without episodes; smoke tests lack behavioural checks (confirmed)

**Source:** `tests/test_g1_dex3.py:24-36`; `tests/test_pipeline.py:12-15`; `tests/test_e2e_g1.py:4`; `tests/test_live_policy_v1.py:21-23`; `tests/test_real_takes.py:8,28,42`; `tests/test_arm_ik.py:7-8`.

**What happens / reasoning:** `test_all_episodes_within_filter_bounds_and_slew` immediately returns if its glob is empty: pytest counts it as passed. Even with files, empty per-file timelines never exercise the inner assertions. The dry/Inspire test calls methods but has no output assertions; it is an exception smoke test, not verification of movement or freeze semantics. Other asset/data tests use explicit skips, which are visible rather than silent; they should not be misreported as exercised coverage. Tests using `pytest.raises` were not classified as ineffective merely for lacking an `assert` statement.

**Suggested fix:** Explicitly skip missing optional data and fail missing required hardware-gate fixtures; require nonempty trajectories. Add behavioural checks to smoke tests where those behaviours are claimed. Report skip reasons and keep CI's explicit file selection distinct from a full suite.

### F22 — medium — Operational prose disagrees with current limits, dry mode and stop behaviour (confirmed)

**Source / contradictions:**

- `g1/arms_glove.py:6-7` says `.80` maximum / `.9` override ceiling; executable lines 29-30 use `.95` and acceleration `6.0`.
- `g1/live_policy_v2.py:13-14` promises episode-long hold after three blocks and speed at most `.7`; lines 34-35 use `.9` normally / `1.8` Fast, while lines 336-340 only log HOLD and resume when a step passes. No persistent abort is set there.
- `docs/G1_GUIDE.md:37` says dry mode does not move; F09 explains why the executable command contract differs.
- `docs/G1_LIVE.md:9,72` presents a full can cap / private table, whereas line 43 says the shared cap is authoritative. The current `g1/live_policy.py:24,35-48` calls the shared cap function, and `ai/object_profile.py:108-122` delegates to the shared rule. These are incompatible descriptions of the intended cap path; do not combine them into a physical-grasp claim.
- `ai/advisor.py:5-6` says advice only lowers caps, contradicted by F15. `ai/eval_objects.py:4` promises provider-specific credentials, contradicted by F11. `ai/recognize.py:3` calls its timeout hard, contradicted by F17's worker-lifetime distinction.

**Minimal check:** Compare the cited prose and executable assignments/branches with `nl -ba <file>`. These are code/document inconsistencies, not new hardware measurements.

**Suggested fix:** Generate effective limits and mode warnings from runtime configuration, publish path-specific behaviour, and remove stale safety promises. Distinguish software stop/hold, runner watchdog and physical emergency stop.

## Remaining unconfirmed concerns and coverage boundaries

- **medium, UNCONFIRMED — shared workspace-checker race.** `g1/arms_glove.py:142,166-172` and `g1/live_policy_v2.py:153-158,172` invoke the same `WS` from planning and act threads. The shim stores mutable FK state/cache (`tools/g1_windows_runner/winshim/pinocchio/__init__.py:114-126`). If the external checker shares one such Data instance, concurrent `positions/violation` can interleave. The actual checker was not available as tracked code, so no false safety result is asserted. Suggested fix: inspect it and give each thread its own checker or serialise FK access; stress-test with deterministic interleaving.
- **medium, UNCONFIRMED — planner continuous-segment assurance.** `g1/start_path.py:18-24,55-68` uses finite samples. `pts` substitutes actual `q0` for the snapped grid start, so the grid's checked first edge is not necessarily the returned first edge. Runtime bisection checks a candidate endpoint. A violating intermediate physical trajectory was not demonstrated. Suggested fix: validate returned segments from the actual start at the required resolution, including self-collision, and retain runtime validation.
- Reviewed `winshim/turbojpeg.py`, `build_cdds.bat` and `dds_listen.py` as source only; no build, DLL load or DDS connection was run. The shim comparison is not a full proof of equivalence to installed Pinocchio or of all safety geometry.
- `ai/judge_gemini.py` is a post-episode judge, not a direct cap controller. Its strict boolean verdict check is useful; `phases` lacks a full schema check in `_parse`. No control-path exploit is established from judge output. No arbitrary code execution from model text was found in the reviewed paths.
- Object locations/labels are initialised once per episode in V1/V2, not continuously revalidated. Their safe use requires that scene assumptions remain true; this audit did not test moving objects, calibration drift, real frame units or stale-camera timestamps.

## Verification record

Executed from `Junction-audit` on `codex/audit` without changing code:

```sh
env -i PATH=/opt/anaconda3/bin:/usr/bin:/bin RECOGNISE_LOG=off python3 -m pytest tests -q
```

Result: **268 passed, 5 skipped in 32.08 s**. This is the local command's result, not a hardware test or CI claim. The empty environment prevents access to inherited credentials; dependencies were already installed. The suite uses simulation, fakes and loopback fixtures. No dependency or model assets were downloaded.

Additional isolated probes used real pure functions and AST-extracted reader/reset/filter methods, with fake sockets and transport, never constructors that start hardware or inference. Executed results: default/NaN hardware cap `1.0`; NaN direct closures `[1,1,1,0,0]`; stale read retained `.9`; malformed packet `JSONDecodeError`; zero quaternion all NaN; V2 reset retained exhausted waypoint index and next access raised `IndexError`; duplicate backend vote `agree=2, cap=1.0`; string confidence `TypeError`; infinite confidence cap `1.0`; model rigid intent cap `1.0`; advisor NaN confidence cap `.70` without confirmation; zero projection ray `depth_ok=True` with NaN position; fake error body echoed an inert marker. All input numbers are synthetic probe values or the cited source constants.

Compact independent reproduction of core pure-function findings (no service):

```sh
env -i PATH=/opt/anaconda3/bin:/usr/bin:/bin RECOGNISE_LOG=off python3 - <<'PY'
from g1.finger_map import closures
from robot.g1_dex3 import G1Dex3Retargeter
from ai.recognize import recognise
from ai.object_profile import cap_for_votes
from ai.intent_router import apply_intent
from ai.advisor import clean, advice_cap
print(G1Dex3Retargeter().max_closure)
print(G1Dex3Retargeter(max_closure=float('nan')).max_closure)
print(closures([float('nan')]*5, .6))
r = recognise(b'', ['same','same'], registry={
    'same': lambda _: dict(object='stress_ball', confidence=.99, ok=True)})
print(r['agree'], r['cap'])
print(cap_for_votes('stress_ball', float('inf'), 2))
print(apply_intent(dict(action='change_profile', target_profile='rigid', via='model'), 'stress_ball'))
print(advice_cap(clean(dict(object='object', confidence=float('nan'), fragility=0))))
PY
```

## Ten findings to fix before any real-robot test

This is the audit's prioritised recommendation; owners should resolve the findings with offline regressions before an operator/staff-controlled hardware procedure. Additional model findings remain gates for enabling those integrations.

1. **F02:** enforce glove freshness, loss handling and deliberate resumption.
2. **F03:** reject malformed/nonfinite fingers, positions and quaternions at input and output boundaries.
3. **F01:** require a finite explicit initial hardware closure limit; no full-range default.
4. **F04:** retain calibrated table/box protection and validate the effective Fast configuration.
5. **F05:** refuse hardware startup without the workspace checker.
6. **F06:** reset startup paths correctly and discard old planner-thread results.
7. **F07:** synchronise V1 IK state with every accepted/scaled command.
8. **F08:** apply self-collision checks throughout startup and escape, not just normal tracking.
9. **F09:** separate compute-only dry mode from a validated, explicitly enabled hold command.
10. **F20:** make offline safety gates fail on clips, aborts, missing progress and shim mismatches.
