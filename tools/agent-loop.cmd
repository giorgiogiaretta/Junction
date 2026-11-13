@echo off
rem Run the agent loop from a normal terminal (cmd/PowerShell). Usage: tools\agent-loop.cmd Giorgio
if "%~1"=="" (echo usage: tools\agent-loop.cmd YourName & exit /b 1)
set "PATH=%PATH%;C:\Program Files\GitHub CLI;%APPDATA%\npm"
cd /d "%~dp0.."
"C:\Program Files\Git\bin\bash.exe" tools/agent-loop.sh %1
