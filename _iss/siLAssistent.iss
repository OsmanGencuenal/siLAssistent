#ifndef MyVersion
  #define MyVersion "0.1.0"
#endif
#ifndef DistDir
  #define DistDir "..\build_out\siLAssistent.dist"
#endif
#ifndef WizardImageDir
  #define WizardImageDir "..\build_out\installer-images"
#endif
#define SupportMail ReadIni(AddBackslash(DistDir) + "siLAssistent.ini", "APPLICATION", "supportMail")
[Setup]
AppId={{4C4E6775-BFE0-47C5-9AE0-EBB3E025CA86}
AppName=siLAssistent
UninstallDisplayIcon={app}\icons\Support.ico
SetupIconFile=..\icons\Support.ico
WizardImageFile={#WizardImageDir}\wizard.bmp
WizardSmallImageFile={#WizardImageDir}\wizard-small.bmp
WizardImageStretch=no
DisableWelcomePage=no
AppVersion={#MyVersion}
DefaultDirName={localappdata}\Programs\siLAssistent
DisableDirPage=no
DefaultGroupName=siLAssistent
PrivilegesRequired=lowest
OutputDir=..\build_out
OutputBaseFilename=siLAssistent_Installer
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
[Dirs]
Name: "{app}\icons"
[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "siLAssistent.ini"
Source: "{#DistDir}\siLAssistent.ini"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall
[INI]
; Only support contact is centrally updated. STATE/USER/PATH are never reset.
Filename: "{app}\siLAssistent.ini"; Section: "APPLICATION"; Key: "supportMail"; String: "{#SupportMail}"

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknüpfung erstellen"; GroupDescription: "Zusätzliche Verknüpfungen:"

[Icons]
Name: "{group}\siLAssistent"; Filename: "{app}\siLAssistent.exe"; IconFilename: "{app}\icons\Support.ico"
Name: "{userdesktop}\siLAssistent"; Filename: "{app}\siLAssistent.exe"; IconFilename: "{app}\icons\Support.ico"; Tasks: desktopicon

Name: "{group}\siLAssistent entfernen"; Filename: "{app}\siLAssistent.exe"; Parameters: "--uninstall ""{uninstallexe}"""; IconFilename: "{app}\icons\Support.ico"

[Run]
Filename: "{app}\siLAssistent.exe"; WorkingDir: "{app}"; Description: "siLAssistent starten"; Flags: nowait postinstall skipifsilent

[InstallDelete]
Type: files; Name: "{userdesktop}\siLAssistent.lnk"; Tasks: not desktopicon
; Remove only obsolete files previously shipped by this installer.
Type: files; Name: "{app}\drivers\148.0.3967.137\msedgedriver.exe"
Type: files; Name: "{app}\drivers\149.0.4022.98\msedgedriver.exe"
Type: files; Name: "{app}\drivers\150.0.4078.144\msedgedriver.exe"
Type: files; Name: "{app}\drivers\151.0.4129.107\msedgedriver.exe"
Type: files; Name: "{app}\drivers\152.0.4191.119\msedgedriver.exe"
Type: filesandordirs; Name: "{app}\selenium\webdriver\common\linux-arm64"
Type: filesandordirs; Name: "{app}\selenium\webdriver\common\linux-x86_64"
Type: filesandordirs; Name: "{app}\selenium\webdriver\common\macos"

[UninstallDelete]
Type: files; Name: "{app}\siLAssistent.ini"
Type: files; Name: "{app}\siLAssistent.ini.lock"
Type: dirifempty; Name: "{app}"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  { ssDone is reached only after a successful installation, including manual runs. }
  if CurStep = ssDone then begin
    if not SetIniString('APPLICATION', 'version', '{#MyVersion}', ExpandConstant('{app}\siLAssistent.ini')) then
      Log('Die installierte Versionsnummer konnte nicht in die lokale INI geschrieben werden.');
  end;
end;

function InitializeUninstall(): Boolean;
var
  Choice, ExitCode: Integer;
  BackupFile, AppDirectory: String;
begin
  Result := False;
  if UninstallSilent then begin
    Result := True;
    Exit;
  end;
  Choice := MsgBox('Möchten Sie Ihre persönlichen Benutzer-Einstellungen vor der Deinstallation als INI exportieren?', mbConfirmation, MB_YESNOCANCEL);
  if Choice = IDCANCEL then Exit;
  if Choice = IDNO then begin
    Result := True;
    Exit;
  end;
  BackupFile := Uppercase(GetUserNameString) + '.ini';
  if not GetSaveFileName('Benutzer-Konfiguration exportieren', BackupFile, ExpandConstant('{userdocs}'), 'INI-Dateien (*.ini)|*.ini', 'ini') then Exit;
  AppDirectory := AddBackslash(ExpandConstant('{app}'));
  if CompareText(Copy(ExpandFileName(BackupFile), 1, Length(AppDirectory)), AppDirectory) = 0 then begin
    MsgBox('Bitte die Sicherung außerhalb des Installationsordners speichern. Die Deinstallation wurde nicht gestartet.', mbError, MB_OK);
    Exit;
  end;
  if not Exec(ExpandConstant('{app}\siLAssistent.exe'), '--export-user-config "' + BackupFile + '"', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ExitCode) then begin
    MsgBox('Der Export konnte nicht gestartet werden. Die Deinstallation wurde nicht gestartet.', mbError, MB_OK);
    Exit;
  end;
  if (ExitCode <> 0) or not FileExists(BackupFile) then begin
    MsgBox('Die Benutzer-Konfiguration konnte nicht gesichert werden. Die Deinstallation wurde nicht gestartet.', mbError, MB_OK);
    Exit;
  end;
  Result := True;
end;
