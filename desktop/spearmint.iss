#define AppVersion "0.5.4"
[Setup]
AppId={{50AE1652-4D38-47A3-9C87-673C2EB13D94}
AppName=Spearmint
AppVersion={#AppVersion}
AppPublisher=Spearmint
DefaultDirName={localappdata}\Programs\Spearmint
DefaultGroupName=Spearmint
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=Spearmint-{#AppVersion}-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=spearmint.ico
UninstallDisplayIcon={app}\Spearmint.exe
CloseApplications=yes
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
[Files]
Source: "..\dist\Spearmint\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "WebView2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall
[Icons]
Name: "{group}\Spearmint"; Filename: "{app}\Spearmint.exe"
Name: "{autodesktop}\Spearmint"; Filename: "{app}\Spearmint.exe"; Tasks: desktopicon
[Run]
Filename: "{tmp}\WebView2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft WebView2 Runtime..."; Flags: waituntilterminated; Check: NeedsWebView2
Filename: "{app}\Spearmint.exe"; Description: "Open Spearmint"; Flags: nowait postinstall skipifsilent; Check: not IsAutoUpdate
Filename: "{app}\Spearmint.exe"; Flags: nowait; Check: IsAutoUpdate
; No UninstallDelete entry: financial data is deliberately preserved.

[Code]
function IsAutoUpdate: Boolean;
begin
  Result := ExpandConstant('{param:SPEARMINTUPDATE|0}') = '1';
end;

function NeedsWebView2: Boolean;
var Version: String;
begin
  Result := True;
  if RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) then
    if (Version <> '') and (Version <> '0.0.0.0') then Result := False;
  if RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) then
    if (Version <> '') and (Version <> '0.0.0.0') then Result := False;
end;
