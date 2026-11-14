# Adding Tommaso's Codex agent without overlapping anyone

Goal: a coding agent in Codex that runs on Tommaso's Mac, pushes from Tommaso's GitHub account (TommyMaggi), and never edits the same files as Claude (this repo's `robot/`, `ai/`) or Giorgio's agents (`Rokoko/`, `ml/`, `vision/`, `g1/`, `docs/RESEARCH_NIGHT.md`, `docs/G1_SIM.md`, `docs/PLAN_QC.md`).

## 1. Ownership: give Codex its own folder
Claude hands `demo/` over: **Codex owns `demo/`** (dashboard, `run_demo.sh`, `results.html`, `overnight.sh`, `morning_check.sh`, `PITCH.md`) and `docs/PITCH*.md`. Claude keeps `robot/` and `ai/`. Add this row to the AGENTS.md table in Codex's first PR and post "claimed" on the board:

| Demo + pitch UI | TommyMaggi (Codex) | `demo/`, `docs/PITCH*.md` |

and change the "Robot + demo + AI" row to "Robot + AI" (`robot/`, `ai/`).

## 2. Setup (once)
```
codex --version                         # not installed on this Mac when checked: install it per OpenAI's instructions, or use the Codex app
cd ~/Junction && git fetch && git worktree add ../Junction-codex -b codex/demo-ui origin/main
cd ../Junction-codex
```
Always work in `../Junction-codex`, never in `~/Junction` (Claude's checkout). One worktree per agent, one branch per task: `codex/<slug>`.

## 3. Non-overlap protocol (every task)
1. `tools/board read -n 10` and `git fetch`; pick one open issue labelled `task` inside Codex's folders.
2. Post: `tools/board post "[Tommaso's Codex] claimed #N, files: demo/..."`. If another post claims a file you need, stop and ask.
3. Edit only `demo/` and `docs/PITCH*.md`. Anything else: post a request to the owner (Claude for `robot/`/`ai/`, Giorgio for the rest).
4. Small commits, branch `codex/<slug>`, PR title starts with `[codex]`, body has `Closes #N`. Run `python3 -m pytest tests -q` before pushing.
5. Do **not** merge your own PR: leave it for Tommaso or Claude to review (CI green is required).
6. After the PR: post the result in one short message, signed `[Tommaso's Codex]`.

## 4. Safety rules
- No API keys in the Codex environment (do not `export VERDA_INFERENCE_KEY` in its shell). It never needs one: it works with mock/replay data.
- Never commit anything from `data/` that is not already tracked; never touch `.env`/keys; no force-push.
- Claims in UI/pitch only if a command in the repo reproduces them; label simulation as simulation and toy numbers as toy (see `demo/results.html`).

## 5. Prompt to paste into Codex
```
You are [Tommaso's Codex] in the Junction hackathon repo (GitHub TommyMaggi; teammate giorgiogiaretta).
Work ONLY in the worktree ../Junction-codex on a branch codex/<slug>. Read AGENTS.md, docs/CODEX_GUIDE.md, docs/DAY2_ATTACK.md, docs/PLAN_QC.md.
You own demo/ and docs/PITCH*.md. Never edit robot/, ai/, Rokoko/, ml/, vision/, g1/.
Task: make demo/results.html the pitch page for the QC product: per-take quality score table (read from data/qc/*.json when it exists, otherwise a clearly labelled empty state), keep/discard with reason, dataset card, and the honest 'proven / not proven' labels already in the page. Offline single file, works at phone width, light/dark.
Before starting: tools/board read -n 10; claim the task on the board. After: python3 -m pytest tests -q, open a PR '[codex] ...' with Closes #N, do not merge it, post the result on the board.
Rules: no API keys, no secrets, small commits, every number must be reproducible by a command in the repo.
```
Headless variant (verify the flag first with `codex exec --help`): `codex exec --full-auto "<the prompt above>"` from `../Junction-codex`.
