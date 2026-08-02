"""Iniciador único do Windows: nunca reutiliza uma versão antiga do servidor."""
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

root = Path(__file__).resolve().parent
address = ("127.0.0.1", 8000)

def stop_previous_server() -> None:
    # O alvo é restrito ao listener local desta aplicação.
    command = "Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
    subprocess.run(["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", command], cwd=root)

def port_available() -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(address)
        return True
    except OSError:
        return False
    finally:
        probe.close()

def open_when_ready() -> None:
    for _ in range(80):
        try:
            with socket.create_connection(address, timeout=0.3):
                webbrowser.open("http://127.0.0.1:8000")
                return
        except OSError:
            time.sleep(0.25)

stop_previous_server()
for _ in range(80):
    if port_available():
        break
    time.sleep(0.25)
else:
    raise SystemExit("A porta local 8000 ainda não foi liberada.")

threading.Thread(target=open_when_ready, daemon=True).start()
import uvicorn
uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False, log_level="warning")
