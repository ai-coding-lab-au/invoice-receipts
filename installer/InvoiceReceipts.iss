#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif

#ifndef MySourceDir
  #define MySourceDir "..\dist\SuperlightInvoice"
#endif

#define MyAppName "Superlight Invoice"
#define MyAppExeName "SuperlightInvoice.exe"

[Setup]
AppId={{6EB50434-4C74-45AA-991E-913486DD33F2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={localappdata}\Programs\SuperlightInvoice
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=auto
AllowNoIcons=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
SetupIconFile=..\branding\superlight-invoice.ico
OutputDir=..\installer-output
OutputBaseFilename=SuperlightInvoice-{#MyAppVersion}-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; The AppId is intentionally unchanged, so this is an in-place upgrade. Remove
; only the obsolete executable left by builds from before the product rename.
Type: files; Name: "{app}\InvoiceReceipts.exe"
Type: files; Name: "{autoprograms}\Invoice & Receipts.lnk"
Type: files; Name: "{autodesktop}\Invoice & Receipts.lnk"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
