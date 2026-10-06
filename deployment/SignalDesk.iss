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
; Tray monitor: start_tray.vbs is launched through wscript.exe (never a console
; window) so the icon can be brought back from the Start Menu after it was
; closed, and it starts automatically with Windows.
Name: "{group}\SignalDesk Tray Monitor"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\deployment\start_tray.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\signaldesk-monitor.ico"; Comment: "Reopen the SignalDesk tray monitor"
Name: "{autostartup}\SignalDesk Tray Monitor"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\deployment\start_tray.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\signaldesk-monitor.ico"; Comment: "Start the SignalDesk tray monitor with Windows"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\deployment\install-service.ps1"""; WorkingDir: "{app}"; Flags: runascurrentuser waituntilterminated

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\deployment\uninstall-service.ps1"""; WorkingDir: "{app}"; Flags: runascurrentuser waituntilterminated
