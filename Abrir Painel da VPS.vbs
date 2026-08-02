Set shell = CreateObject("WScript.Shell")

' Cria uma conexao privada: navegador local -> SSH -> Reels Manager na VPS.
' O painel nunca fica exposto publicamente por este atalho.
command = "powershell.exe -NoProfile -WindowStyle Hidden -Command ""Start-Process -FilePath 'ssh.exe' -ArgumentList @('-N','-o','ExitOnForwardFailure=yes','-L','127.0.0.1:8000:127.0.0.1:8000','root@147.79.87.206') -WindowStyle Hidden; Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:8000'"""
shell.Run command, 0, False
