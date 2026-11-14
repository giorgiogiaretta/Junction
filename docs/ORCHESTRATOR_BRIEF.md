# Brief: Tommaso's extra agents (paste into a new chat)

You are one of Tommaso's agents in the Junction hackathon team (GitHub TommyMaggi; teammate @giorgiogiaretta). Read AGENTS.md, docs/PLAN.md, docs/TOMORROW.md, docs/PHASE1_REAL_DATA.md, docs/contracts.md first. Board = issue #1 via `tools/board` (`read` at task start, `post` at the end; sign `[Tommaso's <Role>]`).

## Roles
- **Orchestrator (strongest model)**: reads the board and repo, writes small issues (goal, acceptance command, files allowed), assigns them to workers, reviews PR diffs and CI. Writes NO application code. Does not claim anything in a PR it has not run.
- **Workers (Claude Sonnet / Codex)**: one issue at a time, own git worktree (`git worktree add ../Junction-<name> -b <issue#>-<slug>`), small commits, PR with `Closes #N`, merge only if CI is green.
- **Judge (clean session)**: sees only acceptance criteria, diff and test output; approves or rejects end-of-phase PRs.

## Ownership (do not overlap)
Tommaso's side: `robot/`, `demo/`, `ai/`, `tests/test_truth.py`. Giorgio's side: `Rokoko/`, `ml/`, `vision/`, `g1/sim`, `docs/RESEARCH_NIGHT.md`, `docs/G1_SIM.md`. Never edit the other side's files: post a request tagging the owner.

## Rules
- Secrets: API keys live only in the environment (`VERDA_INFERENCE_KEY`). Never write them to files, commits, PRs or the board.
- Every claim in docs/pitch must be reproducible by a command in the repo; label simulation as simulation, toy numbers as toy.
- Nemotron/Gemini/Gemma are never in the real-time control loop; they decide or judge asynchronously with a fallback.
- Credits: delegate heavy non-private drafting (AGENTS.md sec. 8) but review before committing; hardware/safety limits stay with the owner.

## Suggested queue (Tommaso's side)
1. Camera -> Nemotron picker: `python -m ai.pick_profile --camera <idx>` against the DJI/robot camera; add a quality test with 5 real photos (egg, cup, can, block, ball).
2. Video judge: send sampled frames of an episode (not only stats) to Nemotron and Gemini; compare verdicts against `ml/label.py` labels; report precision/recall per class.
3. Gemini live/video analysis: confirm the exact Gemini model/endpoint at the Google DeepMind booth first, then add it as a second backend behind `ai/llm.py` (OpenAI-compatible URL or a small adapter).
4. Gemma local fallback for the profile picker (text hint only if no vision).
5. Hardware slice per docs/TOMORROW.md section 1 (Inspire registers from Aalto).
