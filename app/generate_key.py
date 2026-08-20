"""Gera uma chave Fernet local e a salva no .env sem imprimir segredos."""
from cryptography.fernet import Fernet
from .config import ROOT
path=ROOT/".env"; rows=path.read_text(encoding="utf-8").splitlines()
key=Fernet.generate_key().decode(); changed=False
out=[]
for row in rows:
    if row.startswith("APP_ENCRYPTION_KEY="):
        out.append("APP_ENCRYPTION_KEY="+key); changed=True
    else: out.append(row)
if not changed: out.append("APP_ENCRYPTION_KEY="+key)
path.write_text("\n".join(out)+"\n",encoding="utf-8")
