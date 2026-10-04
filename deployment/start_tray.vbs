Option Explicit

Dim fileSystem, shell, fso, projectRoot, trayScript, python
Dim candidates, i, j, current, pathVar, pathParts, candidate

Set fileSystem = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

projectRoot = fileSystem.GetParentFolderName(fileSystem.GetParentFolderName(WScript.ScriptFullName))
trayScript = projectRoot & "\deployment\system_tray.py"

candidates = Array( _
    projectRoot & "\.venv\Scripts\pythonw.exe", _
    projectRoot & "\venv\Scripts\pythonw.exe", _
    projectRoot & "\.venv\Scripts\python.exe", _
    projectRoot & "\venv\Scripts\python.exe" )

For i = 0 To UBound(candidates)
    If fso.FileExists(candidates(i)) Then
        python = candidates(i)
        Exit For
    End If
Next

If python = "" Then
    pathVar = shell.ExpandEnvironmentStrings("%PATH%")
    pathParts = Split(pathVar, ";")
    For j = 0 To UBound(pathParts)
        current = Trim(pathParts(j))
        If Len(current) > 0 Then
            If InStr(1, current, "\", vbBinaryCompare) = 0 Then
                current = shell.ExpandEnvironmentStrings(current)
            End If
            candidate = fso.BuildPath(current, "pythonw.exe")
            If fso.FileExists(candidate) Then
                python = candidate
                Exit For
            End If
        End If
    Next
End If

If python = "" Then
    MsgBox "SignalDesk Monitor needs Python 3.11 or newer." & vbCrLf & vbCrLf & _
           "No Python was found next to SignalDesk or on PATH." & vbCrLf & vbCrLf & _
           "The SignalDeskServer Windows service keeps working without this tool.", _
           vbExclamation, "SignalDesk Monitor"
    WScript.Quit 1
End If

If Not fso.FileExists(trayScript) Then
    MsgBox "SignalDesk Monitor could not find:" & vbCrLf & trayScript, _
           vbCritical, "SignalDesk Monitor"
    WScript.Quit 1
End If

shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & trayScript & Chr(34), 0, False