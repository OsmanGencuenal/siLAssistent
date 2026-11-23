param(
    [switch]$PrepareOnly,
    [switch]$CheckOnly,
    [switch]$LocalOnly,
    [switch]$CreateInstaller,
    [string]$PublishDirectory = "",
    [string]$InstallerCopyDirectory = "\\smtcft0028prj.rd.corpintra.net\me7work$\Projekte\M286\04_Software_EDL\30_SiL\004_Tools",
    [string]$ISCC = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root
if ($CreateInstaller -and -not $PrepareOnly -and -not $CheckOnly) {
    if (-not $ISCC) {
        $Compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($Compiler) { $ISCC = $Compiler.Source }
        if (-not $ISCC) {
            $InnoCandidates = @()
            foreach ($InstallBase in @((Join-Path $env:LOCALAPPDATA "Programs"), ${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
                if ($InstallBase) { $InnoCandidates += Join-Path $InstallBase "Inno Setup 6\ISCC.exe" }
            }
            foreach ($RegistryRoot in @("HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")) {
                foreach ($Installation in Get-ChildItem -LiteralPath $RegistryRoot -ErrorAction SilentlyContinue | Get-ItemProperty -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "Inno Setup 6*" -and $_.InstallLocation }) {
                    $InnoCandidates += Join-Path $Installation.InstallLocation "ISCC.exe"
                }
            }
            $ISCC = $InnoCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
        }
    }
    if (-not $ISCC -or -not (Test-Path -LiteralPath $ISCC -PathType Leaf)) { throw "Inno Setup 6 wurde nicht gefunden. Bitte installieren oder -ISCC mit dem vollständigen Pfad zu ISCC.exe angeben." }
    Write-Host "Inno-Compiler: $ISCC"
}
$Python = Join-Path $Root ".build-env\Scripts\python.exe"
$Lock = Join-Path $Root "requirements-build.lock"
$env:PYTHONNOUSERSITE = "1"
if (-not (Test-Path -LiteralPath $Python)) {
    if ($CheckOnly) { throw "Build-Umgebung fehlt. Zuerst -PrepareOnly ausführen." }
    & py -3.13 -m venv (Join-Path $Root ".build-env")
    if ($LASTEXITCODE -ne 0) { throw "64-Bit-Python 3.13 wird benötigt." }
}
& $Python -c "import sys; assert sys.version_info[:2] == (3,13) and sys.maxsize > 2**32"
if ($LASTEXITCODE -ne 0) { throw "Falsches Build-Python." }
if (-not $CheckOnly) {
    & $Python -m pip install --disable-pip-version-check -r $Lock
    if ($LASTEXITCODE -ne 0) { throw "Build-Abhängigkeiten konnten nicht eingerichtet werden." }
}
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw "Inkonsistente Build-Abhängigkeiten." }
& $Python -c "import importlib.metadata as m; assert m.version('PySide6').strip() == '6.9.2'; assert m.version('Nuitka').strip() == '4.3.1'; import win32com.client"
if ($LASTEXITCODE -ne 0) { throw "Release-Profil stimmt nicht mit dem Lockfile überein." }
$env:QT_QPA_PLATFORM = "offscreen"
$env:QT_QPA_FONTDIR = Join-Path $env:WINDIR "Fonts"
& $Python (Join-Path $Root "tools\run_tests.py")
if ($LASTEXITCODE -ne 0) { throw "Regressionstests fehlgeschlagen." }
if ($CheckOnly) { exit 0 }
$Out = Join-Path $Root "build_out"
New-Item -ItemType Directory -Path $Out -Force | Out-Null
$SourceReport = Join-Path $Out "source-smoke.json"
& $Python source/siLAssistent.py --self-test $SourceReport
if ($LASTEXITCODE -ne 0) { throw "Source-Funktionstest fehlgeschlagen." }
if ($PrepareOnly) { exit 0 }
if ($PublishDirectory -and ($LocalOnly -or -not $CreateInstaller)) {
    throw "Veröffentlichung erfordert -CreateInstaller und darf nicht mit -LocalOnly kombiniert werden."
}
$Tag = [guid]::NewGuid().ToString("N")
$Stage = Join-Path $Root "build\src-$Tag"
New-Item -ItemType Directory -Path $Stage -Force | Out-Null
# Only runtime Python and catalog data enter the source snapshot.
$SourceRoot = Join-Path $Root "source"
foreach ($File in Get-ChildItem -LiteralPath $SourceRoot -Recurse -File | Where-Object { $_.Extension -in @(".py", ".json") -and $_.FullName -notmatch '[\\/]__pycache__[\\/]' }) {
    $Relative = $File.FullName.Substring($SourceRoot.Length + 1)
    $Destination = Join-Path (Join-Path $Stage "source") $Relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Copy-Item -LiteralPath $File.FullName -Destination $Destination
}
& $Python (Join-Path $Root "tools\sync_update_ini.py")
if ($LASTEXITCODE -ne 0) { throw "Die lokale Update-INI konnte nicht mit der LW-INI synchronisiert werden." }
& $Python (Join-Path $Root "tools\embed_build_settings.py") (Join-Path $Stage "source\core\build_settings.py")
if ($LASTEXITCODE -ne 0) { throw "Build-Einstellungen konnten nicht eingebettet werden. supportMail/silverLicences lokal und [PATH] in der LW-INI prüfen." }
$Entry = Join-Path $Stage "source\siLAssistent.py"
Copy-Item -LiteralPath (Join-Path $Root "VERSION") -Destination $Stage
& $Python -c "import runpy; from source.core.config import Config; settings=runpy.run_path(r'$Stage\source\core\build_settings.py'); Config.export_installation_config(r'$Stage\siLAssistent.ini', paths=settings['RELEASE_PATHS'], support_mail=settings['SUPPORT_MAIL'])"
if ($LASTEXITCODE -ne 0) { throw "Installationskonfiguration konnte nicht vorbereitet werden." }
$SeleniumManager = (& $Python -c "from pathlib import Path; import selenium; print(Path(selenium.__file__).parent / 'webdriver/common/windows/selenium-manager.exe')").Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $SeleniumManager)) { throw "Selenium Manager fehlt im Build-Profil." }
$Version = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw).Trim()
$Nuitka = @("-m", "nuitka", "--standalone", "--enable-plugin=pyside6", "--msvc=latest",
    "--windows-console-mode=disable", "--windows-icon-from-ico=$Root\icons\Main.ico",
    "--product-name=siLAssistent", "--file-description=siLAssistent - Installation und Update",
    "--product-version=$Version", "--file-version=$Version",
    "--include-data-files=$Root\icons\Main.ico=icons/Main.ico",
    "--include-data-files=$Root\icons\Support.ico=icons/Support.ico",
    "--include-data-files=$Root\icons\assistant.ico=icons/assistant.ico",
    "--include-data-files=$Root\icons\assistant.svg=icons/assistant.svg",
    "--include-data-files=$Root\icons\assistant.png=icons/assistant.png",
    "--include-package=source", "--include-package=win32com",
    "--nofollow-import-to=pytest", "--nofollow-import-to=_pytest", "--nofollow-import-to=tests", "--nofollow-import-to=*.tests", "--nofollow-import-to=comtypes.test", "--nofollow-import-to=win32com.test",
    "--include-package=grpc", "--include-package=google.protobuf", "--include-module=google._upb._message",
    "--nofollow-import-to=silver_grpc", "--nofollow-import-to=remotesilverapi",
    "--noinclude-data-files=selenium/webdriver/common/linux-arm64/*",
    "--noinclude-data-files=selenium/webdriver/common/linux-x86_64/*",
    "--noinclude-data-files=selenium/webdriver/common/macos/*",
    "--include-package=selenium", "--include-package=pywinauto", "--include-package=comtypes",
    # Nuitka already bundles Selenium Manager as an executable via its selenium package rule.
    "--include-module=pythoncom", "--include-module=pywintypes", "--include-module=win32timezone",
    "--output-filename=siLAssistent.exe", "--output-dir=$Out", "--report=$Out\compilation-report.xml",
    "--include-data-files=$Stage\source\inca\catalog.json=source/inca/catalog.json",
    "--include-data-files=$Stage\source\silver\catalog.json=source/silver/catalog.json",
    "--include-data-files=$Stage\VERSION=VERSION",
    "--include-data-files=$Stage\siLAssistent.ini=siLAssistent.ini", $Entry)
$PreviousPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = $Stage
    Push-Location -LiteralPath $Stage
    try { & $Python @Nuitka } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { throw "Nuitka-Build fehlgeschlagen." }
} finally { $env:PYTHONPATH = $PreviousPath }
$Dist = Join-Path $Out "siLAssistent.dist"
$Exe = Join-Path $Dist "siLAssistent.exe"
# Keep every offline Edge version, but unpack only the matching driver at runtime.
& $Python (Join-Path $Root "tools\package_runtime.py") (Join-Path $Root "drivers") $Dist
if ($LASTEXITCODE -ne 0) { throw "Die Laufzeitdateien konnten nicht platzsparend vorbereitet werden." }
# Fail before installer creation if development artifacts leaked into the package.
& $Python (Join-Path $Root "tools\check_distribution.py") $Dist
if ($LASTEXITCODE -ne 0) { throw "Auslieferungsordner enthält Entwicklungsdateien oder benötigte Laufzeitdateien fehlen." }
$ExeReport = Join-Path $Out "exe-smoke.json"
& (Join-Path $Root "tools\\test_standalone.ps1") -DistributionPath $Dist -ReportPath $ExeReport
$Source = Get-Content -LiteralPath $SourceReport -Raw | ConvertFrom-Json
$Compiled = Get-Content -LiteralPath $ExeReport -Raw | ConvertFrom-Json
foreach ($Field in @("silver_license_servers", "multiprocessing", "version", "inca_methods", "silver_methods", "launcher_ui", "setup_ui", "state_ini", "git_jira", "catalog_hashes")) {
    if (($Source.$Field | ConvertTo-Json -Compress) -ne ($Compiled.$Field | ConvertTo-Json -Compress)) {
        throw "Source und EXE weichen ab: $Field"
    }
}
$StageSettings = Join-Path $Stage "source\core\build_settings.py"
$ExpectedPathsJson = & $Python -c "import runpy,json,sys; print(json.dumps(runpy.run_path(sys.argv[1])['RELEASE_PATHS']))" $StageSettings
if ($LASTEXITCODE -ne 0) { throw "Release-Pfade konnten nicht geprüft werden." }
$ExpectedPaths = $ExpectedPathsJson | ConvertFrom-Json
foreach ($Key in @("silverInstallerPath", "silSetupPath", "GitInstallationPath", "GitSetupRepo")) {
    if ($Compiled.release_paths.$Key -ne $ExpectedPaths.$Key) { throw "EXE enthält einen falschen Release-Pfad: $Key" }
}
if (-not $Compiled.ok) { throw "EXE-Prüfbericht ist nicht erfolgreich." }
if ($CreateInstaller) {
    $Version = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -Raw).Trim()
    $WizardImages = Join-Path $Stage "installer-images"
    & $Python (Join-Path $Root "tools\prepare_installer_images.py") (Join-Path $Root "icons\Support.ico") $WizardImages
    if ($LASTEXITCODE -ne 0) { throw "Installerbilder konnten nicht aus Support.ico erzeugt werden." }
    & $ISCC "/DWizardImageDir=$WizardImages" "/DMyVersion=$Version" "/DDistDir=$Dist" (Join-Path $Root "_iss\siLAssistent.iss")
    if ($LASTEXITCODE -ne 0) { throw "Installer-Build fehlgeschlagen." }
    if ($InstallerCopyDirectory -and -not $LocalOnly) {
        $Installer = Join-Path $Out "siLAssistent_Installer.exe"
        if (-not (Test-Path -LiteralPath $InstallerCopyDirectory -PathType Container)) {
            throw "Der Installer ist lokal fertig, aber der Zielordner ist nicht erreichbar: $InstallerCopyDirectory"
        }
        $CopiedInstaller = Join-Path $InstallerCopyDirectory "siLAssistent_Installer.exe"
        $TemporaryInstaller = Join-Path $InstallerCopyDirectory ("siLAssistent_Installer." + [guid]::NewGuid().ToString("N") + ".partial")
        try {
            Copy-Item -LiteralPath $Installer -Destination $TemporaryInstaller
            $LocalHash = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash
            if ((Get-FileHash -LiteralPath $TemporaryInstaller -Algorithm SHA256).Hash -ne $LocalHash) {
                throw "Die Installer-Kopie auf dem LW stimmt nicht mit der lokalen Datei überein."
            }
            Move-Item -LiteralPath $TemporaryInstaller -Destination $CopiedInstaller -Force
            Write-Host "Installer auf dem LW abgelegt und SHA-256 geprüft: $CopiedInstaller"
            # A version announcement alone cannot be installed by existing clients.
            # Publish the verified path + digest in the default build as well.
            $ReleaseManifest = Join-Path $InstallerCopyDirectory "ini\siLAssistent_Update.ini"
            foreach ($UpdateIni in @($ReleaseManifest, (Join-Path $Root "siLAssistent_Update.ini"))) {
                & $Python (Join-Path $Root "tools\write_release_manifest.py") --output $UpdateIni --version $Version --installer $CopiedInstaller --sha256 $LocalHash
                if ($LASTEXITCODE -ne 0) { throw "Update-INI konnte nicht vollständig veröffentlicht werden: $UpdateIni" }
            }
            Write-Host "Update-Version, Installer-Pfad und SHA-256 lokal und auf dem LW veröffentlicht."
        } finally {
            if (Test-Path -LiteralPath $TemporaryInstaller) { Remove-Item -LiteralPath $TemporaryInstaller }
        }
    }
    if ($PublishDirectory) {
        $Installer = Join-Path $Out "siLAssistent_Installer.exe"
        $ReleaseDir = Join-Path $PublishDirectory "siLAssistent\releases\$Version"
        New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null
        $RemoteInstaller = Join-Path $ReleaseDir "siLAssistent_Installer.exe"
        if (Test-Path -LiteralPath $RemoteInstaller) { throw "Version bereits veröffentlicht; VERSION erhöhen." }
        Copy-Item -LiteralPath $Installer -Destination $RemoteInstaller
        $Hash = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
        if ((Get-FileHash -LiteralPath $RemoteInstaller -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Hash) {
            throw "Netzwerkkopie stimmt nicht mit lokalem Installer überein."
        }
        $Manifest = Join-Path $PublishDirectory "ini\siLAssistent_Update.ini"
        & $Python (Join-Path $Root "tools\write_release_manifest.py") --output $Manifest --version $Version --installer $RemoteInstaller --sha256 $Hash
        if ($LASTEXITCODE -ne 0) { throw "Update-INI konnte nicht veröffentlicht werden." }
    }
}
Write-Host "Erfolgreich gebaut und geprüft: $Exe"
