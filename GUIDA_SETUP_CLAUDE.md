# Setup guide for your Claude (Junction hackathon team)

You are a coding agent helping a teammate of Giorgio at the Junction hackathon (Finland). Follow these steps with your human. Do not enter passwords or tokens for them: they run `gh auth login` themselves.

## Context
- Team repo (private): https://github.com/giorgiogiaretta/Junction
- Challenge: Rokoko Smartgloves (see `Rokoko/README.md`). Gloves capture hand/finger motion, not touch or force.
- Rokoko links: https://www.rokoko.com/mocap/junction-hackathon (SDK docs, knowledge base, a Skill .MD for LLMs). Questions: #rokoko channel on the Junction Discord. Hardware is at the venue's hardware lab.
- Agents coordinate on ONE pinned GitHub issue (the "Message Board", issue #1), using `tools/board`.

## Setup (about 5 minutes)
1. Install the requirements if missing: `git`, GitHub CLI (`gh`), and `bash` (Git Bash on Windows).
2. The human accepts Giorgio's collaborator invitation to the repo (check email or https://github.com/giorgiogiaretta/Junction/invitations).
3. The human runs `gh auth login` once (GitHub.com, HTTPS, browser login).
4. Clone: `gh repo clone giorgiogiaretta/Junction` and `cd Junction`.
5. Verify: `tools/board whoami` should print their GitHub login. Then `tools/board read -n 5`.
6. Read `AGENTS.md` fully. It is the rule set for every agent (board etiquette, owned folders, branch/PR workflow).
7. If `BOARD_ISSUE` is not 1, set `export BOARD_ISSUE=<number>`.

## How to work
- Start each task with `tools/board unread`. Keep one background `tools/board wait` running and re-arm it after each wake.
- Post as `[<Human>'s Claude] short message`. Tag teammates by GitHub login, e.g. `@giorgiogiaretta`.
- Only edit folders you own (table in `AGENTS.md`). To touch someone else's, ask on the board first.
- Branch `<issue#>-<slug>`, small commits, stage only your own files, PR with `Closes #N`, `git fetch` and rebase before pushing, never force-push shared branches.
- Use `--repo giorgiogiaretta/Junction` with `gh issue`/`gh pr` if `gh` picks the wrong repo.

## First message to post
`tools/board post "[<Human>'s Claude] set up, ready. Which folder/area do I own?"`
