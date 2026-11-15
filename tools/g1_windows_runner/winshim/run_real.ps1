# Runner on the REAL G1 from Windows. Policy must already be listening on ws://localhost:8000.
# Usage: & C:\Users\giorg\Desktop\aaltonomous-humanoid\winshim\run_real.ps1 [-Seconds 120]
param([int]$Seconds = 120, [switch]$NoCamera)
# High priority: the runner process also runs the 250 Hz arm control thread (xr_teleoperate); under load its loop stretched
# to ~100 ms and the robot lagged the commands by ~1 s (14/11 night logs). Children inherit the priority class.
try { [System.Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'High' } catch {}
$root = "C:\Users\giorg\Desktop\aaltonomous-humanoid"
$env:PATH = "$root\third_party\cyclonedds\install\bin;$env:PATH"
$env:PYTHONPATH = "$root\winshim;$root"
Set-Location $root
# DDS needs the adapter NAME that holds the robot-network IP (changes with the USB-Ethernet dongle: "Ethernet 5", "Ethernet 6", ...)
$iface = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object IPAddress -like "192.168.123.*" | Select-Object -First 1).InterfaceAlias
if (-not $iface) { Write-Host "no adapter with IP 192.168.123.x: set the IP (see start_g1.ps1)" -ForegroundColor Red; return }
Write-Host "robot network on: $iface"
# camera computer (PC2): head RGB-D server on :55560. It was .164 on day 1, .254 on 14/11 night: take the first that answers.
$cam = $null
foreach ($h in @($env:G1_CAM_IP, "192.168.123.164", "192.168.123.254") | Where-Object { $_ }) {
    if (Test-NetConnection $h -Port 55560 -InformationLevel Quiet -WarningAction SilentlyContinue) { $cam = $h; break }
}
if ($cam) { Write-Host "camera (PC2) at: $cam" -ForegroundColor Green } else { Write-Host "camera (PC2) NOT found (.164/.254 :55560): no image" -ForegroundColor Yellow; $cam = "192.168.123.164" }
if ($NoCamera) {   # runner's own options: no head RGB-D, image server on localhost (nothing there) = no image decoding at all
    Write-Host "camera DISABLED (less load)" -ForegroundColor Yellow
    py -3.11 -m aaltonomous.deploy.runner --backend real --policy ws://localhost:8000 --team giorgio --episodes 1 --network-interface "$iface" --img-server-ip 127.0.0.1 --no-head-rgbd --time-limit $Seconds
} else {
    py -3.11 -m aaltonomous.deploy.runner --backend real --policy ws://localhost:8000 --team giorgio --episodes 1 --network-interface "$iface" --img-server-ip $cam --time-limit $Seconds
}
