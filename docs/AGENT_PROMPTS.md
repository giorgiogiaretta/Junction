# Prompts for Tommaso's extra agents (14/11)

Folders and ownership (no overlap): Giorgio = `Rokoko/ ml/ vision/ g1/`; Tommaso's Claude (Sonnet) = `ai/ robot/`; Codex-1 = `demo/ docs/PITCH*.md`; Codex-2 = `cv/`; **Docs agent = `docs/ARCHITECTURE.md`, `docs/submission/`, root `README.md`**; **PM agent = nothing in the repo** (writes STATUS.md locally + one board post per round). Fable = audit only (`docs/ORCH_BACKLOG.md`).

## Docs agent (Sonnet, Claude Code app, folder ~/Junction-docs, branch docs/submission)
```
git worktree add ../Junction-docs -b docs/submission origin/main
```
Prompt: see the chat message where it was given; core rules: owns only docs/ARCHITECTURE.md, docs/submission/*, root README.md; every claim must point to a command or document in the repo and use the safe wording of docs/ORCH_BACKLOG.md section 1; no keys; PR, do not merge.

## PM / watchdog (terminal, own worktree, read-only)
```
git worktree add ../Junction-pm -b pm/watch origin/main
cd ../Junction-pm && bash tools/pm-loop.sh
```
Prompt lives in docs/PM_PROMPT.md. Reads `docs/DEADLINE.md` for the real deadline (Tommaso must create it).
