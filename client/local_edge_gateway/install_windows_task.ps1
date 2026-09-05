$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $PSScriptRoot
$Python=(Get-Command python.exe).Source
$Action=New-ScheduledTaskAction -Execute $Python -Argument "-m client.local_edge_gateway.cli run" -WorkingDirectory $Root
$Trigger=New-ScheduledTaskTrigger -AtStartup
$Principal=New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName 'AssetTrack360EdgeGateway' -Action $Action -Trigger $Trigger -Principal $Principal -Force | Out-Null
Write-Host 'AssetTrack 360 Edge Gateway startup task installed.'
