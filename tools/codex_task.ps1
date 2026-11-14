# Run one Codex task (desktop app's CLI, Giorgio's ChatGPT login) in the separate worktree ../Junction-gcodex.
# Codex can READ and WRITE files there (workspace-write sandbox) but its sandbox cannot execute Python on this PC (access denied to
# the user's Python install): Codex writes the code, Claude runs it, reviews the diff and commits.
#   powershell -File tools/codex_task.ps1 -Task "text"      (or -TaskFile path)    -> ../Junction-gcodex/codex_logs/<time>.log
param([string]$Task = "", [string]$TaskFile = "")
$pkg = Get-AppxPackage -Name "OpenAI.Codex" -ErrorAction SilentlyContinue | Select-Object -First 1
$exe = if ($pkg) { Join-Path $pkg.InstallLocation "app\resources\codex.exe" } else { "C:\Program Files\WindowsApps\OpenAI.Codex_26.1111.2228.0_x64__2p2nqsd0c76g0\app\resources\codex.exe" }
if (-not (Test-Path $exe)) { Write-Output "codex.exe not found: install/update the Codex desktop app"; exit 1 }
$wt = Resolve-Path (Join-Path $PSScriptRoot "..\..\Junction-gcodex")
if ($TaskFile) { $Task = Get-Content $TaskFile -Raw }
$pre = "You work in $wt (git worktree, branch codex/grasp-search). Read AGENTS.md and the files named in the task first. IMPORTANT: your sandbox cannot run Python on this machine; do not try to run code or tests. Write the code carefully, keep changes to the files the task names, do not commit or push, and finish with a summary: files changed, what to run to test it, open questions. Task: "
New-Item -ItemType Directory -Force (Join-Path $wt "codex_logs") | Out-Null
$log = Join-Path $wt ("codex_logs\" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")
Set-Location $wt
& $exe exec -s workspace-write --skip-git-repo-check ($pre + $Task) *>&1 | Out-File -Encoding utf8 $log
Write-Output "codex finished: $log"
