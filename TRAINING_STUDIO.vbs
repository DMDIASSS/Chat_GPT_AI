' Double-click to launch the Studio without a console. No administrator access.
Option Explicit
Dim shell, fso, root, py, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
py = root & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(py) Then
  MsgBox "Missing project Python: " & py & vbCrLf & "Use TRAINING_STUDIO.bat for startup details.", vbExclamation, "Training Studio"
Else
  shell.CurrentDirectory = root
  command = Chr(34) & py & Chr(34) & " " & Chr(34) & root & "\slater_training_studio.py" & Chr(34)
  shell.Run command, 0, False
End If
