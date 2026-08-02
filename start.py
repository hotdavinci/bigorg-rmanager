"""Supervisor local: relança o servidor quando o painel solicita reinício."""
import subprocess
import sys
import time

while True:
    result = subprocess.run([sys.executable, "-m", "app"], cwd=__file__.rsplit("\\", 1)[0])
    if result.returncode != 75:
        break
    time.sleep(0.8)
