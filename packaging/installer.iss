#define MyAppName "TPS AI Trading Assistant"
#define MyAppVersion "1.4.1"
#define MyAppPublisher "Tapas Kumar Pahar"
#define MyAppExeName "TPS AI Trading Assistant.exe"

[Setup]
AppId={{4E04311B-86B2-4925-A17C-27967D357CB0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} Release 1.4.1 (20-08-2026)
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\TPS AI Trading Assistant
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=TPS-AI-Trading-Assistant-Setup-1.4.1
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName} Release 1.4.1
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\TPS AI Trading Assistant\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
