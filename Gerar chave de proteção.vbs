Option Explicit
Dim shell, fs, folder, pythonw
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
pythonw = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python314\pythonw.exe"
shell.CurrentDirectory = folder
shell.Run """" & pythonw & """ -m app.generate_key", 0, True
MsgBox "A chave local de proteção foi criada.", 64, "Reels Automation Manager"
