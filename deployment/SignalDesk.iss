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
Source: "..\*"; DestDir: "{app}"; Excludes: ".git,*.db,logs,__pycache__,.venv,venv,node_modules,frontend\node_modules"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SignalDesk"; Filename: "msedge.exe"; Parameters: "--app=http://127.0.0.1:8000 --window-size=1440,900"; WorkingDir: "{app}"; IconFilename: "{app}\assets\signaldesk-monitor.ico"
Name: "{group}\SignalDesk Monitor"; Filename: "wscript.exe"; Parameters: """{app}\deployment\start_tray.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\signaldesk-monitor.ico"
Name: "{commondesktop}\SignalDesk"; Filename: "msedge.exe"; Parameters: "--app=http://127.0.0.1:8000 --window-size=1440,900"; WorkingDir: "{app}"; IconFilename: "{app}\assets\signaldesk-monitor.ico"
Name: "{commondesktop}\SignalDesk Monitor"; Filename: "wscript.exe"; Parameters: """{app}\deployment\start_tray.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\signaldesk-monitor.ico"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\deployment\install-service.ps1"""; WorkingDir: "{app}"; Flags: runascurrentuser waituntilterminated

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\deployment\uninstall-service.ps1"""; WorkingDir: "{app}"; Flags: runascurrentuser waituntilterminated
