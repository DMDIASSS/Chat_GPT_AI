Option Explicit
Dim sh, fs, root, py, script
Set sh = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
root = fs.GetParentFolderName(WScript.ScriptFullName)
py = fs.BuildPath(root, "..\..\.venv\Scripts\pythonw.exe")
script = fs.BuildPath(root, "hub_app.py")
If Not fs.FileExists(py) Then
  MsgBox "Python virtual environment not found: " & py, vbExclamation, "Research Hub"
Else
  sh.CurrentDirectory = root
  sh.Run """" & py & """ """ & script & """", 0, False
End If
