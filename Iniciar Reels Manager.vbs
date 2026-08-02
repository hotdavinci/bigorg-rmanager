' Inicia a aplicação sem abrir uma janela de terminal.
Option Explicit
Dim shell, fs, folder, python, command
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
folder = fs.GetParentFolderName(WScript.ScriptFullName)
python = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python314\python.exe"

If Not fs.FileExists(python) Then
  MsgBox "Não encontrei o Python necessário para iniciar o Reels Manager. Execute 'Preparar Reels Manager.bat' uma vez.", 48, "Reels Automation Manager"
  WScript.Quit 1
End If

command = "cmd.exe /c " & Chr(34) & Chr(34) & python & Chr(34) & " " & Chr(34) & folder & "\launch.pyw" & Chr(34) & Chr(34)
shell.CurrentDirectory = folder
shell.Run command, 0, False
