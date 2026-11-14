# Runner on the REAL G1 from Windows. Policy must already be listening on ws://localhost:8000.
# Usage: & C:\Users\giorg\Desktop\aaltonomous-humanoid\winshim\run_real.ps1 [-Seconds 120]
param([int]$Seconds = 120)
$root = "C:\Users\giorg\Desktop\aaltonomous-humanoid"
$env:PATH = "$root\third_party\cyclonedds\install\bin;$env:PATH"
$env:PYTHONPATH = "$root\winshim;$root"
Set-Location $root
py -3.11 -m aaltonomous.deploy.runner --backend real --policy ws://localhost:8000 --team giorgio --episodes 1 --network-interface "Ethernet 5" --time-limit $Seconds
