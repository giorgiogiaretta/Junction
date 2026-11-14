# V2 (con Coil): due mani, uovo + lattina vuota. Servono driver Rokoko in esecuzione, guanti + Coil.
# Uso: .\run.ps1 [argomenti extra per teleop_multi.py]   es.  .\run.ps1 --calib
param([Parameter(ValueFromRemainingArguments = $true)] $Rest)
if (-not $Rest) { $Rest = @("--cam") }
Set-Location (Join-Path $PSScriptRoot "..\..")
py -3.11 g1\sim\teleop_multi.py @Rest
