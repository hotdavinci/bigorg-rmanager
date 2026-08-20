from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

class Base(DeclarativeBase): pass
settings.data_dir.mkdir(parents=True, exist_ok=True)
# SQLite aceita apenas um escritor por vez.  Um timeout curto evita falhas
# transitórias quando o scheduler, OAuth e a preparação de um lote chegam juntos.
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False, "timeout": 30})
@event.listens_for(engine, "connect")
def sqlite_wal(conn, _):
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
Session = sessionmaker(engine, expire_on_commit=False)
