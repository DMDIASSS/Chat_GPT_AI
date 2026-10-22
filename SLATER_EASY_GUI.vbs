Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
shell.Run "cmd /c """ & folder & "\SLATER_EASY.bat"" gui" , 0, False
