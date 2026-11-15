# ONE command to run the G1 with the gloves (arms + hands, fast version) and the operator console.
#   & C:\Users\giorg\Desktop\Junction\start_g1.ps1            (fast version g1/arms_glove.py)
#   & C:\Users\giorg\Desktop\Junction\start_g1.ps1 -Safe      (slow version g1/arms_simple.py, tested on the robot 14/11)
# Opens: Rokoko driver (if not running), operator console (gloves -> UDP 14043, camera, robot view), the policy;
# then runs the organisers' runner HERE: press Enter at "Place the cubes", Ctrl+C to stop.
#   & C:\Users\giorg\Desktop\Junction\start_g1.ps1 -Vision    (camera + Tommaso's vision: the arm goes over the object it sees,
#                                                              glove closed = descend + grasp; object default stress_ball,
#                                                              -Right egg / -Left can_empty to change; no camera -> 35 cm / +-15 cm)
#   & C:\Users\giorg\Desktop\Junction\start_g1.ps1 -Coil      (Coil Pro: the robot arm follows your wrist, as the simulator.
#                                                              Seated calibration FIRST (beeps), then the robot goes to "hands open,
#                                                              palm down, in front"; right hand only, -Both for both hands;
#                                                              -NoCalib to reuse the last calibration)
#   -NoConsole: no operator console (less CPU = less delay)
#   -Fast: staff-approved (15/11) faster limits: runner arm speed 2.0 rad/s, no counter keep-out (robot-vs-robot collision kept)
#   -NoCamera: the runner does not read the camera streams (less load on this PC = the robot follows with less delay)
#   -CoilVision: like -Coil but g1/live_policy_v2_vision.py (Codex+DeepSeek review: the head camera recognises the object; caps egg 0.50, can 0.90, ball 1.0)
#   -LowLag: runner process with the bit-identical fast CRC (winshim/lowlag.py): fixes the ~1 s stale robot state that made
#            the arms lag and move in steps (docs/ARM_DELAY.md). Performance only, no safety rule changed. Off by default
#            until confirmed on the robot.
param([switch]$Safe, [switch]$Vision, [switch]$Coil, [switch]$CoilVision, [switch]$Both, [switch]$NoCalib, [switch]$NoConsole, [switch]$NoCamera, [switch]$Fast, [switch]$LowLag, [int]$Seconds = 300, [string]$Closure = "0.6",
      [ValidateSet("stress_ball", "can_empty", "egg")][string]$Right = "stress_ball",
      [ValidateSet("stress_ball", "can_empty", "egg")][string]$Left = "stress_ball")
$J = "C:\Users\giorg\Desktop\Junction"
if ($CoilVision) { $Coil = [switch]$true }
if ($Fast) { $env:G1_FAST = "1"; Write-Host "FAST MODE (staff-approved): arms 2 rad/s, no table zone; robot self-collision check ON" -ForegroundColor Yellow } else { Remove-Item Env:G1_FAST -ErrorAction SilentlyContinue }
if ($LowLag) { $env:G1_LOWLAG = "1" } else { Remove-Item Env:G1_LOWLAG -ErrorAction SilentlyContinue }
# the runner loads its shims from the organisers' folder: keep them in sync with this checkout's copy
Copy-Item -Force "$PSScriptRoot\tools\g1_windows_runner\winshim\*.py", "$PSScriptRoot\tools\g1_windows_runner\winshim\run_real.ps1" "C:\Users\giorg\Desktop\aaltonomous-humanoid\winshim\" -ErrorAction SilentlyContinue
$ErrorActionPreference = "Continue"

Write-Host "== 1/5 robot network" -ForegroundColor Cyan
$ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object IPAddress -like "192.168.123.*" | Select-Object -First 1
if (-not $ip) {
    $eth = (Get-NetAdapter | Where-Object { $_.Status -eq "Up" -and $_.Name -like "Ethernet*" } | Select-Object -First 1).Name
    Write-Host "No IP on the robot cable. Open PowerShell as ADMINISTRATOR and run:" -ForegroundColor Red
    Write-Host "  New-NetIPAddress -InterfaceAlias `"$eth`" -IPAddress 192.168.123.222 -PrefixLength 24"
    Write-Host "Then run this script again."; return
}
$env:G1_IFACE = $ip.InterfaceAlias
if (-not (Test-Connection 192.168.123.161 -Count 1 -Quiet)) { Write-Host "Robot (192.168.123.161) NOT reachable: cable, robot on, VPN off?" -ForegroundColor Red; return }
$cam = (Test-NetConnection 192.168.123.164 -Port 55560 -InformationLevel Quiet -WarningAction SilentlyContinue) -or (Test-NetConnection 192.168.123.254 -Port 55560 -InformationLevel Quiet -WarningAction SilentlyContinue)
Write-Host ("robot ok; head camera (PC2 .164 or .254): " + $(if ($cam) { "OK" } else { "off: no image, everything else works" }))

Write-Host "== 2/5 Rokoko glove driver" -ForegroundColor Cyan
if (-not (Get-Process rokoko-sdk -ErrorAction SilentlyContinue)) {
    Start-Process "$env:LOCALAPPDATA\Rokoko Device SDK\bin\rokoko-sdk.exe" -ArgumentList "--auto-stream-usb"; Start-Sleep 3
}
Write-Host "driver ok"

Write-Host "== 3/5 freeing port 8000 and starting the console" -ForegroundColor Cyan
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'arms_glove|arms_simple|live_policy|rgmp_client|teleop_multi' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
if ($NoConsole) { Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'tools[\\/]console[\\/]app.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }
elseif (-not (Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'tools[\\/]console[\\/]app.py' })) {
    Start-Process py -ArgumentList "-3.11", "$J\tools\console\app.py" -WorkingDirectory $J
}

Write-Host "== 4/5 policy" -ForegroundColor Cyan
$src = "udp:14043"
if ($Coil) {
    # Coil: wrist pose + fingers come from rgmp_client on UDP 14044 (the console keeps reading the driver too: tested, both get 83 Hz)
    Start-Process powershell -WorkingDirectory $J -ArgumentList "-NoExit", "-Command", "py -3.11 Rokoko/src/rgmp_client.py --hand any --udp-port 14044"
    Write-Host "OPEN and CLOSE both hands for 8 seconds (finger calibration)..." -ForegroundColor Yellow; Start-Sleep 10
    $hands = if ($Both) { "--right $Right --left $Left" } else { "--right $Right" }
    if (-not $NoCalib) {
        Write-Host "CALIBRATION (follow the prompts and beeps): hand flat and still on the table, forward, back, left, then hands OPEN palm down in front of you" -ForegroundColor Yellow
        Push-Location $J; py -3.11 g1/live_policy_v2.py --source udp:14044 --calib $hands.Split(" "); $ok = $LASTEXITCODE; Pop-Location
        if ($ok -ne 0) { Write-Host "calibration failed: run the script again" -ForegroundColor Red; return }
    }
    $pol = if ($CoilVision) { "g1/live_policy_v2_vision.py" } else { "g1/live_policy_v2.py" }; $src = "udp:14044"; $extra = "$hands --right-xy 0.35,-0.15 --left-xy 0.35,0.15"
} else {
    $pol = if ($Safe) { "g1/arms_simple.py" } elseif ($Vision) { "g1/live_policy_v1.py" } else { "g1/arms_glove.py" }
    $extra = if ($Vision) { "--right $Right --left $Left --right-xy 0.35,-0.15 --left-xy 0.35,0.15" } else { "" }
}
Start-Process powershell -WorkingDirectory $J -ArgumentList "-NoExit", "-Command", "`$env:G1_MAX_CLOSURE='$Closure'; py -3.11 $pol --source $src --host 0.0.0.0 $extra"
$t0 = Get-Date
while (-not (Test-NetConnection 127.0.0.1 -Port 8000 -InformationLevel Quiet -WarningAction SilentlyContinue)) {
    if (((Get-Date) - $t0).TotalSeconds -gt 90) { Write-Host "the policy did not start: check its window" -ForegroundColor Red; return }
    Start-Sleep 2
}
Write-Host "policy ready ($pol, max closure $Closure)"

Write-Host "== 5/5 runner on the robot: GLOVES OPEN, emergency stop in hand, then Enter at 'Place the cubes'" -ForegroundColor Yellow
try { [System.Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'High' } catch {}
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'live_policy|arms_glove|arms_simple|rgmp_client' -and $_.Name -match 'python' } | ForEach-Object { try { (Get-Process -Id $_.ProcessId).PriorityClass = 'High' } catch {} }
& "C:\Users\giorg\Desktop\aaltonomous-humanoid\winshim\run_real.ps1" -Seconds $Seconds -NoCamera:$NoCamera -LowLag:$LowLag
