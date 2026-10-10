Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python311\pythonw.exe"
If Not fso.FileExists(sh) Then
    MsgBox "Python 3.11 pythonw.exe not found. Use CURRICULUM_3_START_DEBUG.bat first.", 48, "Curriculum"
Else
    shell.CurrentDirectory = dir
    shell.Run """" & sh & """ """ & dir & "\curriculum_app.py" & """", 1, False
End If
