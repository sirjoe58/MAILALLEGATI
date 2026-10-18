; Programma di installazione di MailAllegati (Inno Setup 6)
; L'installazione non prosegue se non si accettano le avvertenze (pagina "Contratto di licenza").

#define AppName "MailAllegati"
#define AppVersion "1.4.0"

[Setup]
AppId={{6E3C8A41-2B7D-4F0A-9C55-3D1E8B7A2F10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=MailAllegati
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=MailAllegati-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\MailAllegati.exe

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"; LicenseFile: "LEGGIMI_AVVERTENZE.txt"
Name: "english"; MessagesFile: "compiler:Default.isl"; LicenseFile: "WARNINGS_EN.txt"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\MailAllegati.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "LEGGIMI_AVVERTENZE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "WARNINGS_EN.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MailAllegati"; Filename: "{app}\MailAllegati.exe"
Name: "{group}\Avvertenze e condizioni d'uso"; Filename: "{app}\LEGGIMI_AVVERTENZE.txt"; Languages: italian
Name: "{group}\Warnings and terms of use"; Filename: "{app}\WARNINGS_EN.txt"; Languages: english
Name: "{group}\{cm:UninstallProgram,MailAllegati}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MailAllegati"; Filename: "{app}\MailAllegati.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MailAllegati.exe"; Description: "{cm:LaunchProgram,MailAllegati}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "reg.exe"; Parameters: "delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v MailAllegati /f"; Flags: runhidden; RunOnceId: "TogliAvvio"
