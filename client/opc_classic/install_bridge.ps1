$ErrorActionPreference='Stop'
if (-not [Environment]::Is64BitOperatingSystem) { Write-Host '32-bit Windows detected' }
Write-Host 'AssetTrack 360 OPC Classic Windows Bridge preflight'
Write-Host ('OS: ' + [Environment]::OSVersion.VersionString)
Write-Host ('PowerShell: ' + $PSVersionTable.PSVersion)
Write-Host ('64-bit OS: ' + [Environment]::Is64BitOperatingSystem)
Write-Host ('64-bit Process: ' + [Environment]::Is64BitProcess)
Write-Host 'Install the OPC vendor Core Components and matching 32/64-bit OPC DA proxy/stub before enabling the bridge.'
Write-Host 'Configure DCOM locally according to the site security policy. Do not expose DCOM to the internet.'
python -m client.opc_classic.windows_preflight
