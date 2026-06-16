# Windows installer for the reverse-ssh tunnel agent. Run in an elevated PowerShell.
#
#   $env:PORTAL_URL='https://PORTAL'; $env:ENROLL_TOKEN='xxxx'
#   irm $env:PORTAL_URL/static/install.ps1 | iex
#
# Requires: Python 3 on PATH and the Windows OpenSSH client (ssh.exe).
$ErrorActionPreference = 'Stop'

$PortalUrl   = $env:PORTAL_URL;   if (-not $PortalUrl)   { throw 'Set $env:PORTAL_URL' }
$EnrollToken = $env:ENROLL_TOKEN; if (-not $EnrollToken) { throw 'Set $env:ENROLL_TOKEN' }
$InstallDir  = 'C:\Program Files\reverse-ssh-agent'
$ConfigDir   = 'C:\ProgramData\reverse-ssh-agent'
$TaskName    = 'ReverseSshAgent'

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { throw 'Python 3 is required on PATH' }
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
  throw 'OpenSSH client (ssh.exe) is required. Install via: Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0'
}

New-Item -ItemType Directory -Force -Path $InstallDir, $ConfigDir | Out-Null
Write-Host 'Downloading agent...'
Invoke-WebRequest -UseBasicParsing -Uri "$PortalUrl/static/agent.py" -OutFile "$InstallDir\agent.py"

Write-Host 'Enrolling with portal...'
& $py "$InstallDir\agent.py" enroll --portal $PortalUrl --token $EnrollToken --config $ConfigDir

Write-Host 'Registering scheduled task (runs at startup as SYSTEM)...'
$action  = New-ScheduledTaskAction -Execute $py -Argument "`"$InstallDir\agent.py`" run --config `"$ConfigDir`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Done. Manage with: Get-ScheduledTask -TaskName $TaskName"
