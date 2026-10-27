# Let the Tessera cloud server use this laptop's GPU, over Tailscale only (v4 Phase 1b, hybrid).
#
# Run once, in PowerShell **as Administrator**:
#     powershell -ExecutionPolicy Bypass -File scripts\expose-ollama-tailscale.ps1
#
# Ollama has no password, so it must never be reachable from the internet or the Wi-Fi. This makes it
# listen on all interfaces (OLLAMA_HOST) and then lets in only Tailscale's private range
# (100.64.0.0/10) through Windows Firewall; any broader rule for Ollama is disabled.
# Undo: setx OLLAMA_HOST "" ; Remove-NetFirewallRule -DisplayName "Ollama via Tailscale only"

$ErrorActionPreference = "Stop"
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Run this in PowerShell as Administrator." -ForegroundColor Yellow; exit 1
}

Write-Host "==> Ollama listens on all interfaces (the firewall decides who gets in)"
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:11434", "User")

Write-Host "==> Disabling broader inbound rules for Ollama"
Get-NetFirewallRule -Direction Inbound -Enabled True -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -match "ollama" -and $_.DisplayName -ne "Ollama via Tailscale only" } |
    ForEach-Object { Disable-NetFirewallRule -Name $_.Name; Write-Host "    disabled: $($_.DisplayName)" }

Write-Host "==> Allowing TCP 11434 from Tailscale addresses only"
Remove-NetFirewallRule -DisplayName "Ollama via Tailscale only" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "Ollama via Tailscale only" -Direction Inbound -Action Allow `
    -Protocol TCP -LocalPort 11434 -RemoteAddress 100.64.0.0/10 -Profile Any | Out-Null

Write-Host "==> Restarting Ollama"
Get-Process -Name "ollama*" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
$app = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama app.exe"
if (Test-Path $app) { Start-Process $app } else { Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden }
Start-Sleep -Seconds 5

$ts = (& "C:\Program Files\Tailscale\tailscale.exe" ip -4) 2>$null
try { Invoke-RestMethod "http://$($ts):11434/api/tags" -TimeoutSec 5 | Out-Null; Write-Host "Ollama answers on Tailscale at http://$($ts):11434" -ForegroundColor Green }
catch { Write-Host "Ollama is not answering on $ts yet; open Ollama from the Start menu and re-run." -ForegroundColor Yellow }
