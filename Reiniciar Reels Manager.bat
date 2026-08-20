@echo off
powershell.exe -NoProfile -WindowStyle Hidden -Command "Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 1"
call "%~dp0Iniciar Reels Manager.bat"
