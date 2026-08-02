"""Relança o supervisor após o processo web liberar a porta local."""
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parent
time.sleep(1.2)
subprocess.Popen([sys.executable, "-m", "app"], cwd=root)
