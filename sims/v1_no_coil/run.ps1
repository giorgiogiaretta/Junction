# V1 (senza Coil). Uso: .\run.ps1 [live|e2e|search|coverage|perceive] [argomenti extra]
param([string]$Mode = "live", [Parameter(ValueFromRemainingArguments = $true)] $Rest)
$sim = Join-Path $PSScriptRoot "..\..\g1\sim"
$script = switch ($Mode) {
  "live"     { "live_sim.py" }
  "e2e"      { "demo_e2e.py" }
  "search"   { "grasp_search.py" }
  "coverage" { "coverage.py" }
  "perceive" { "perceive.py" }
  default    { throw "Modo sconosciuto: $Mode (live|e2e|search|coverage|perceive)" }
}
if ($Mode -eq "live" -and -not $Rest) { $Rest = @("--obj", "egg", "--replay", "77", "--cam") }
Set-Location (Join-Path $PSScriptRoot "..\..")
py -3.11 (Join-Path $sim $script) @Rest
