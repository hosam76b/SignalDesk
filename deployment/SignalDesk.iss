[Setup]
AppName=SignalDesk
AppVersion=1.0.0
DefaultDirName={autopf}\SignalDesk
DefaultGroupName=SignalDesk
OutputDir=..\releases
OutputBaseFilename=SignalDesk_Setup
Compression=lzma
SolidCompression=yes
SetupIconFile=..\assets\signaldesk-monitor.ico
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\*"; DestDir: "{app}"; Excludes: ".git,.github,*.db,*.db-shm,*.db-wal,logs,__pycache__,.venv,venv,node_modules,releases,tests,test_*.py,innosetup-*.exe,frontend\.next,tools\nssm\nssm-2.24\src,tools\nssm\nssm-2.24\*.txt"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SignalDesk"; Filename: "http://127.0.0.1:8000"; IconFilename: "{app}\assets\signaldesk-monitor.ico"
Name: "{autodesktop}\SignalDesk"; Filename: "http://127.0.0.1:8000"; IconFilename: "{app}\assets\signaldesk-monitor.ico"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\deployment\install-service.ps1"""; WorkingDir: "{app}"; Flags: runascurrentuser waituntilterminated

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\deployment\uninstall-service.ps1"""; WorkingDir: "{app}"; Flags: runascurrentuser waituntilterminated
