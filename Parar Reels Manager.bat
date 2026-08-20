@echo off
REM Encerra somente o processo local que estiver usando 127.0.0.1:8000.
powershell.exe -NoProfile -WindowStyle Hidden -Command "Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
exit
