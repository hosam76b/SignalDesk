Option Explicit

Dim fileSystem, projectRoot, python, trayScript, shell

Set fileSystem = CreateObject("Scripting.FileSystemObject")
projectRoot = fileSystem.GetParentFolderName(fileSystem.GetParentFolderName(WScript.ScriptFullName))
python = projectRoot & "\.venv\Scripts\python.exe"
trayScript = projectRoot & "\deployment\system_tray.py"
Set shell = CreateObject("WScript.Shell")

shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & trayScript & Chr(34), 0, False