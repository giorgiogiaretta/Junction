# Team rules for every agent

## 1. The board (pinned GitHub issue)

Every agent reads and posts on the pinned "Message Board" issue via `tools/board` (needs only `gh`, logged in). Set `BOARD_ISSUE` if it is not issue #1.

- Start every post with `[<human>'s <agent>]`, e.g. `[Sam's Codex]`. Keep it short: what changed, which files or contracts, what you need, from whom.
- Mention by GitHub login. Team: `@giorgiogiaretta` (Giorgio, lead), `@TommyMaggi` (Tommaso), `@all` (everyone). Add new teammates here.
- **Mentions you or `@all`:** act on it and reply promptly.
- **Not addressed to you:** still read it. Reassess your own work only if it is affected (a contract, a file you own, something already done). Do not redo finished work, and do not reply just to acknowledge.
- Before editing another teammate's files, post the request on the board tagging the owner. Do not wait on a human: the owner's agent decides and replies (see section 5).

Polling is incremental (about one cheap API call per poll, 30 s default) so a shared token stays under GitHub's rate limit. Commands: `tools/board unread` (new posts, marks read; flags MENTION), `tools/board read -n 20`, `tools/board post "[Name's Agent] text"` (or pipe stdin), `tools/board wait` (blocks until someone else posts), `tools/board whoami`.

**Stay in the loop:**
- Claude Code: the committed hooks (`.claude/settings.json`) show unread posts at session start and on every prompt. Keep one background `tools/board wait` running and re-arm it after each wake.
- Everything else: run `tools/board unread` at task start, before each commit, and after merges. Or run a terminal loop: `while tools/board wait; do <your agent CLI invocation>; done`.

## 2. Chain of command

Giorgio (`@giorgiogiaretta`) is the lead. Agents work autonomously and do NOT stop to ask humans for routine decisions: they decide, post on the board, and continue. Escalate to a human only for destructive or irreversible actions (deleting data, force-push, spending money, publishing outside the repo).

## 3. Workflow

1. Pick or file an issue. Comment on it or post on the board when you take it.
2. Branch `<issue#>-<slug>` from fresh `main`.
3. Small commits. Stage only your own files (no `git add -A`).
4. Open a PR with `Closes #N`. The author merges their own PR once it works locally.
5. Always `git fetch` and rebase before pushing. Never force-push shared branches.
6. If a merge changes something other teammates depend on (an API, a schema, an env var), post on the board when it lands.

## 4. Who owns what (automatic)

Ownership is claimed, not assigned. If a folder has no owner, the first agent that needs it adds a row here, commits, and posts `[Name's Agent] claimed <folder>` on the board. Pick folders by function: `Rokoko/src` (glove capture/recording), `ml/` (models), `robot/` (hardware control), `demo/` (dashboard, pitch). Default split: Giorgio's agent takes `ml/` and `Rokoko/src`; Tommaso's agent takes `robot/` and `demo/`; anyone may claim what is still free.

| Area | Owner (GitHub login) | Folders |
|---|---|---|
| Capture + ML | giorgiogiaretta | `Rokoko/`, `ml/` |
| Robot + demo | TommyMaggi | `robot/`, `demo/` |

## 5. Autonomous collaboration

- **Need something from a teammate?** Post on the board tagging them with a concrete request ("@TommyMaggi expose `set_fingers([5 floats 0-1])` in `robot/`"). Keep working on something else meanwhile.
- **Got tagged?** Handle it immediately: do it, or reply with a short counter-proposal. Silence is not allowed. If the request touches your folder, you decide.
- **Disagreement:** the owner of the folder wins; on shared interfaces the lead's agent decides and posts the final contract.
- **Contracts:** write interfaces (function signatures, JSON schemas, ports) in `docs/contracts.md` and post when they change.
- **Delegation:** every agent may delegate heavy, non-private work to cheaper models (`delegate` MCP: DeepSeek/Qwen/Gemini) and must review the result before committing. Never send personal data to delegates.
- **Wake-ups:** each teammate runs `tools/agent-loop.sh` on their machine; it sleeps on `tools/board wait` and starts a headless Claude when someone posts or tags.

## 6. Model routing for delegation (automatic, agent chooses)

Use the `delegate` MCP tool; the agent picks the model per job, no human approval:
- `gemini-pro`: long reading/summaries, large context, planning drafts, review of big diffs.
- `gemini-flash`: cheap bulk reading, formatting, boilerplate, docs.
- `qwen-max`: multi-file code, refactors, debugging.
- `deepseek`: new code, math, algorithm design.
- Disagreement or high-stakes choice: send the same question blind to two models, adopt on agreement, otherwise design a quick experiment.
- Always review delegate output before committing. Delegates cannot browse: paste the needed doc text. No personal data to delegates.
- Gemini CLI and Antigravity are not usable headless here; use `delegate` only.

## 7. Backlog (agents self-assign from GitHub issues labeled `task`; claim on the board)

Humans may be away at stands: keep going without them, post progress on the board.
