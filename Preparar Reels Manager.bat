@echo off
title Preparando Reels Automation Manager
cd /d "%~dp0"
echo Instalando os componentes necessarios. Esta etapa e feita apenas uma vez.
python -m pip install -e .
if errorlevel 1 goto erro
cd frontend
call npm.cmd install
if errorlevel 1 goto erro
call npm.cmd run build
if errorlevel 1 goto erro
cd ..
start "" wscript.exe "%~dp0Iniciar Reels Manager.vbs"
exit /b 0
:erro
echo.
echo Nao foi possivel preparar o programa. Verifique se Python e Node.js estao instalados.
pause
