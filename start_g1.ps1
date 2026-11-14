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
param([switch]$Safe, [switch]$Vision, [switch]$Coil, [switch]$Both, [switch]$NoCalib, [int]$Seconds = 300, [string]$Closure = "0.6",
      [ValidateSet("stress_ball", "can_empty", "egg")][string]$Right = "stress_ball",
      [ValidateSet("stress_ball", "can_empty", "egg")][string]$Left = "stress_ball")
$J = "C:\Users\giorg\Desktop\Junction"
$ErrorActionPreference = "Continue"

Write-Host "== 1/5 rete del robot" -ForegroundColor Cyan
$ip = Get-NetIPAddress -InterfaceAlias "Ethernet 5" -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object IPAddress -like "192.168.123.*"
if (-not $ip) {
    Write-Host "MANCA l'IP sul cavo del robot. Apri PowerShell come AMMINISTRATORE e lancia:" -ForegroundColor Red
    Write-Host '  New-NetIPAddress -InterfaceAlias "Ethernet 5" -IPAddress 192.168.123.222 -PrefixLength 24'
    Write-Host "(se l'adattatore ha un altro nome: Get-NetAdapter). Poi rilancia questo script."; return
}
if (-not (Test-Connection 192.168.123.161 -Count 1 -Quiet)) { Write-Host "Robot (192.168.123.161) NON raggiungibile: cavo, robot acceso, NordVPN spento?" -ForegroundColor Red; return }
$cam = Test-Connection 192.168.123.164 -Count 1 -Quiet
Write-Host ("robot ok; camera testa (PC2 .164): " + $(if ($cam) { "OK" } else { "spenta: niente immagine, il resto funziona" }))

Write-Host "== 2/5 driver guanti Rokoko" -ForegroundColor Cyan
if (-not (Get-Process rokoko-sdk -ErrorAction SilentlyContinue)) {
    Start-Process "$env:LOCALAPPDATA\Rokoko Device SDK\bin\rokoko-sdk.exe" -ArgumentList "--auto-stream-usb"; Start-Sleep 3
}
Write-Host "driver ok"

Write-Host "== 3/5 libero la porta 8000 e avvio la console" -ForegroundColor Cyan
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'arms_glove|arms_simple|live_policy|rgmp_client|teleop_multi' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
if (-not (Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'tools[\\/]console[\\/]app.py' })) {
    Start-Process py -ArgumentList "-3.11", "$J\tools\console\app.py" -WorkingDirectory $J
}

Write-Host "== 4/5 policy" -ForegroundColor Cyan
$src = "udp:14043"
if ($Coil) {
    # Coil: wrist pose + fingers come from rgmp_client on UDP 14044 (the console keeps reading the driver too: tested, both get 83 Hz)
    Start-Process powershell -WorkingDirectory $J -ArgumentList "-NoExit", "-Command", "py -3.11 Rokoko/src/rgmp_client.py --hand any --udp-port 14044"
    Write-Host "APRI e CHIUDI entrambe le mani per 8 secondi (taratura dita)..." -ForegroundColor Yellow; Start-Sleep 10
    $hands = if ($Both) { "--right $Right --left $Left" } else { "--right $Right" }
    if (-not $NoCalib) {
        Write-Host "CALIBRAZIONE (segui le scritte e i bip): mano piatta e ferma sul tavolo, avanti, ritorno, sinistra, poi mani APERTE palmo in giu' davanti a te" -ForegroundColor Yellow
        Push-Location $J; py -3.11 g1/live_policy_v2.py --source udp:14044 --calib $hands.Split(" "); $ok = $LASTEXITCODE; Pop-Location
        if ($ok -ne 0) { Write-Host "calibrazione non riuscita: rilancia lo script" -ForegroundColor Red; return }
    }
    $pol = "g1/live_policy_v2.py"; $src = "udp:14044"; $extra = "$hands --right-xy 0.35,-0.15 --left-xy 0.35,0.15"
} else {
    $pol = if ($Safe) { "g1/arms_simple.py" } elseif ($Vision) { "g1/live_policy_v1.py" } else { "g1/arms_glove.py" }
    $extra = if ($Vision) { "--right $Right --left $Left --right-xy 0.35,-0.15 --left-xy 0.35,0.15" } else { "" }
}
Start-Process powershell -WorkingDirectory $J -ArgumentList "-NoExit", "-Command", "`$env:G1_MAX_CLOSURE='$Closure'; py -3.11 $pol --source $src --host 0.0.0.0 $extra"
$t0 = Get-Date
while (-not (Test-NetConnection 127.0.0.1 -Port 8000 -InformationLevel Quiet -WarningAction SilentlyContinue)) {
    if (((Get-Date) - $t0).TotalSeconds -gt 90) { Write-Host "la policy non parte: guarda la sua finestra" -ForegroundColor Red; return }
    Start-Sleep 2
}
Write-Host "policy pronta ($pol, chiusura max $Closure)"

Write-Host "== 5/5 runner sul robot: GUANTI APERTI, arresto di emergenza in mano, poi Invio a 'Place the cubes'" -ForegroundColor Yellow
& "C:\Users\giorg\Desktop\aaltonomous-humanoid\winshim\run_real.ps1" -Seconds $Seconds
