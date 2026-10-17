Option Explicit
Dim shell, files, root, command
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = root
command = Chr(34) & root & "\.venv\Scripts\python.exe" & Chr(34) & " " & Chr(34) & root & "\slater_freestyle.py" & Chr(34) & " gui --settings " & Chr(34) & root & "\FREESTYLE_SETTINGS.json" & Chr(34)
shell.Run command, 0, False
