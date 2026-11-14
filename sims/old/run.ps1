# Vecchie simulazioni. Uso: .\run.ps1 [video|physics|kinematic] [argomenti extra]
param([string]$Mode = "video", [Parameter(ValueFromRemainingArguments = $true)] $Rest)
$script = switch ($Mode) {
  "video"     { "demo_video.py" }
  "physics"   { "grasp_physics.py" }
  "kinematic" { "g1_sim.py" }
  default     { throw "Modo sconosciuto: $Mode (video|physics|kinematic)" }
}
if ($Mode -eq "physics" -and -not $Rest) { $Rest = @("--levels", "0,0.2,0.3,0.4,0.5,0.55,0.6,0.65,0.7,0.75,0.8,0.9,1.0", "--render") }
Set-Location (Join-Path $PSScriptRoot "..\..")
py -3.11 (Join-Path "g1\sim" $script) @Rest
