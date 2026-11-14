# Runner on the REAL G1 from Windows. Policy must already be listening on ws://localhost:8000.
# Usage: & C:\Users\giorg\Desktop\aaltonomous-humanoid\winshim\run_real.ps1 [-Seconds 120]
param([int]$Seconds = 120)
$root = "C:\Users\giorg\Desktop\aaltonomous-humanoid"
$env:PATH = "$root\third_party\cyclonedds\install\bin;$env:PATH"
$env:PYTHONPATH = "$root\winshim;$root"
Set-Location $root
# DDS needs the adapter NAME that holds the robot-network IP (changes with the USB-Ethernet dongle: "Ethernet 5", "Ethernet 6", ...)
$iface = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object IPAddress -like "192.168.123.*" | Select-Object -First 1).InterfaceAlias
if (-not $iface) { Write-Host "nessun adattatore con IP 192.168.123.x: imposta l'IP (vedi start_g1.ps1)" -ForegroundColor Red; return }
Write-Host "rete robot su: $iface"
py -3.11 -m aaltonomous.deploy.runner --backend real --policy ws://localhost:8000 --team giorgio --episodes 1 --network-interface "$iface" --time-limit $Seconds
