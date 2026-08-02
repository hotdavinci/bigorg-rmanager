Option Explicit
Dim shell, fs, folder
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
shell.Run "notepad.exe """ & folder & "\.env""", 1, False
