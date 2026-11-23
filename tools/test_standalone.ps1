param(
    [Parameter(Mandatory=$true)][string]$DistributionPath,
    [Parameter(Mandatory=$true)][string]$ReportPath
)
$ErrorActionPreference = "Stop"
$Dist = (Resolve-Path -LiteralPath $DistributionPath).Path
$Exe = Join-Path $Dist "siLAssistent.exe"
if (-not (Test-Path -LiteralPath $Exe)) { throw "Vollstaendiger Standalone-Ordner fehlt." }
$Report = [System.IO.Path]::GetFullPath($ReportPath)
New-Item -ItemType Directory -Path (Split-Path -Parent $Report) -Force | Out-Null
$Sandbox = Join-Path $env:TEMP ("siLAssistent-portable-test-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $Sandbox -Force | Out-Null
$Names = @("PATH","PYTHONPATH","PYTHONHOME","PYTHONUSERBASE","PYTHONNOUSERSITE","QT_PLUGIN_PATH","QT_QPA_PLATFORM_PLUGIN_PATH","QML2_IMPORT_PATH","QT_QPA_PLATFORM")
$Previous = @{}
foreach ($Name in $Names) { $Previous[$Name] = [Environment]::GetEnvironmentVariable($Name,"Process") }
try {
    $env:PATH = "$env:WINDIR\System32;$env:WINDIR;$env:WINDIR\System32\Wbem"
    foreach ($Name in @("PYTHONPATH","PYTHONHOME","QT_PLUGIN_PATH","QT_QPA_PLATFORM_PLUGIN_PATH","QML2_IMPORT_PATH")) {
        [Environment]::SetEnvironmentVariable($Name,$null,"Process")
    }
    $env:PYTHONUSERBASE = $Sandbox
    $env:PYTHONNOUSERSITE = "1"
    $env:QT_QPA_PLATFORM = "offscreen"
    $Arguments = "--self-test " + [char]34 + $Report + [char]34
    $Process = Start-Process -FilePath $Exe -ArgumentList $Arguments -WorkingDirectory $Sandbox -WindowStyle Hidden -PassThru
    if (-not $Process.WaitForExit(120000)) {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        throw "Standalone-Selbsttest hat das Zeitlimit ueberschritten."
    }
    if ($Process.ExitCode -ne 0) { throw "Standalone-Selbsttest fehlgeschlagen." }
    $Result = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
    foreach ($Check in @("ok","packaged","self_contained_workers","bundled_runtime","multiprocessing","silver_api_worker","silver_ui_worker", "ui_lifetime","offline_drivers","launcher_ui","setup_ui")) {
        if ($Result.$Check -ne $true) { throw "Standalone-Pruefung fehlgeschlagen: $Check" }
    }
    Write-Host "Standalone-Pruefung ohne Python im PATH erfolgreich: $Report"
} finally {
    foreach ($Name in $Names) { [Environment]::SetEnvironmentVariable($Name,$Previous[$Name],"Process") }
}
