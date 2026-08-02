"""Inicializador silencioso para uso por duplo clique no Windows."""
import socket
import uvicorn

ADDRESS = ("127.0.0.1", 8000)

def already_running() -> bool:
    try:
        with socket.create_connection(ADDRESS, timeout=0.4):
            return True
    except OSError:
        return False

def main() -> None:
    # O arquivo VBS é responsável por abrir o navegador; assim há somente uma aba.
    if not already_running():
        uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False, log_level="warning")

if __name__ == "__main__": main()
