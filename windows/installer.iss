; Programma di installazione di MailAllegati (Inno Setup 6)
; L'installazione non prosegue se non si accettano le avvertenze (pagina "Contratto di licenza").

#define AppName "MailAllegati"
#define AppVersion "1.2"

[Setup]
AppId={{6E3C8A41-2B7D-4F0A-9C55-3D1E8B7A2F10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=MailAllegati
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
LicenseFile=LEGGIMI_AVVERTENZE.txt
OutputDir=dist
OutputBaseFilename=MailAllegati-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\MailAllegati.exe

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "Crea un'icona sul desktop"; GroupDescription: "Icone aggiuntive:"

[Files]
Source: "dist\MailAllegati.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "LEGGIMI_AVVERTENZE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\MailAllegati"; Filename: "{app}\MailAllegati.exe"
Name: "{group}\Avvertenze e condizioni d'uso"; Filename: "{app}\LEGGIMI_AVVERTENZE.txt"
Name: "{group}\Disinstalla MailAllegati"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MailAllegati"; Filename: "{app}\MailAllegati.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MailAllegati.exe"; Description: "Avvia MailAllegati"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "reg.exe"; Parameters: "delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v MailAllegati /f"; Flags: runhidden; RunOnceId: "TogliAvvio"
