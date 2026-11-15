# Entire / CRACI (process): draft

**Not entered:** the CRACI connection was skipped because it needs an organisation-owned repository (`docs/TOMORROW.md`, `docs/SCORECARD.md`). Kept as a process note.

## Story
Two humans, about ten AI agents (Claude, Codex, delegated models) in one repo. Every agent owns folders (`AGENTS.md` section 4), talks on one pinned GitHub issue (`tools/board`), works on a branch per issue, opens PRs, and never claims a number without a command that reproduces it (`docs/ORCH_BACKLOG.md` section 1).

## Evidence
- Board: issue #1 (`tools/board read -n 50`).
- PRs: over 80 in two days (`gh pr list --state all --limit 200 | wc -l`).
- Tests: `python3 -m pytest tests -q`; CI workflow `.github/workflows/truth.yml` (covers only part of the tests, backlog B14).

## Not shown
No external scanning service connected. CI does not run every test file.
