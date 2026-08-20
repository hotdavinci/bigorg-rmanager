' Reinicia somente o processo local que está ouvindo em 127.0.0.1:8000.
Option Explicit
Dim shell, fs, folder, command
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
folder = fs.GetParentFolderName(WScript.ScriptFullName)

command = "powershell.exe -NoProfile -WindowStyle Hidden -Command ""Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"""
shell.Run command, 0, True
WScript.Sleep 700
shell.Run "wscript.exe """ & folder & "\Iniciar Reels Manager.vbs""", 0, False
