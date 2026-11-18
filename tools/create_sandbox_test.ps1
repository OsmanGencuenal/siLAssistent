param(
    [string]$DistributionPath = (Join-Path $PSScriptRoot "..\build_out\siLAssistent.dist"),
    [string]$OutputPath = (Join-Path $PSScriptRoot "..\build_out\siLAssistent-Test.wsb")
)
$ErrorActionPreference = "Stop"
$Dist = (Resolve-Path -LiteralPath $DistributionPath).Path
$Tools = (Resolve-Path -LiteralPath $PSScriptRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $Dist "siLAssistent.exe"))) { throw "Zuerst Standalone-EXE bauen." }
$DistXml = [System.Security.SecurityElement]::Escape($Dist)
$ToolsXml = [System.Security.SecurityElement]::Escape($Tools)
$Command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Copy-Item -LiteralPath C:\Package -Destination C:\siLAssistent-Test -Recurse; &amp; C:\SmokeTools\test_standalone.ps1 -DistributionPath C:\siLAssistent-Test -ReportPath C:\Users\WDAGUtilityAccount\Desktop\siLAssistent-Test.json; Read-Host"'
$Configuration = @"
<Configuration>
  <Networking>Disable</Networking>
  <MappedFolders>
    <MappedFolder><HostFolder>$DistXml</HostFolder><SandboxFolder>C:\Package</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
    <MappedFolder><HostFolder>$ToolsXml</HostFolder><SandboxFolder>C:\SmokeTools</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder>
  </MappedFolders>
  <LogonCommand><Command>$Command</Command></LogonCommand>
</Configuration>
"@
$Destination = [System.IO.Path]::GetFullPath($OutputPath)
New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
[System.IO.File]::WriteAllText($Destination,$Configuration)
Write-Host "Sandbox-Test vorbereitet: $Destination"
