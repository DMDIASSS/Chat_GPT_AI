' Double-click to launch AFK Improved without a console window. No admin privileges.
Option Explicit
Dim shell, fso, root, py, cmd
Set shell=CreateObject("WScript.Shell")
Set fso=CreateObject("Scripting.FileSystemObject")
root=fso.GetParentFolderName(WScript.ScriptFullName)
py=root & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(py) Then
  MsgBox "Missing project Python: " & py & vbCrLf & "Create your .venv first.", vbExclamation, "AFK Improved"
Else
  shell.CurrentDirectory=root
  cmd=Chr(34) & py & Chr(34) & " " & Chr(34) & root & "\afk_improved_desktop.pyw" & Chr(34)
  shell.Run cmd, 0, False
End If
