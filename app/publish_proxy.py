"""Persistent dedicated proxy assignment per Instagram account."""
import hashlib
import json
from pathlib import Path
import sqlite3
from threading import Lock
from urllib.parse import urlsplit


def validate_proxy_url(value: str) -> str:
    """Validate without allowing URL parser errors to expose credentials."""
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.port is None or parsed.query or parsed.fragment
                or parsed.path not in {"", "/"}):
            raise ValueError
    except ValueError:
        raise RuntimeError("Proxy inválido; use HTTP/HTTPS com host e porta") from None
    return value


class PublicationProxyPool:
    """Account keys and URL fingerprints are persisted, never proxy credentials."""
    def __init__(self):
        self._lock = Lock()
        self._configuration = None
        self._pool = ()

    def for_account(self, account_id: str, pool_json: str, fallback: str, database: Path) -> str:
        with self._lock:
            configuration = (pool_json, fallback)
            if configuration != self._configuration:
                try:
                    urls = json.loads(pool_json) if pool_json.strip() else ([fallback.strip()] if fallback.strip() else [])
                    if not isinstance(urls, list) or any(not isinstance(url, str) or not url.strip() for url in urls):
                        raise ValueError
                except (ValueError, TypeError):
                    raise RuntimeError("Configuração de proxies inválida; use lista JSON de URLs") from None
                # Validate/cache the whole pool only when configuration changes.
                self._pool = tuple(dict.fromkeys(validate_proxy_url(url.strip()) for url in urls))
                self._configuration = configuration
            if not self._pool:
                return ""
            if not account_id:
                raise RuntimeError("Conta necessária para selecionar proxy")
            fingerprints = {hashlib.sha256(url.encode()).hexdigest(): url for url in self._pool}
            database = Path(database)
            database.parent.mkdir(parents=True, exist_ok=True)
            try:
                connection = sqlite3.connect(database, timeout=30)
                try:
                    database.chmod(0o600)
                    connection.execute('CREATE TABLE IF NOT EXISTS assignments (account TEXT PRIMARY KEY, proxy_hash TEXT NOT NULL UNIQUE)')
                    connection.execute('BEGIN IMMEDIATE')
                    existing = connection.execute('SELECT proxy_hash FROM assignments WHERE account=?',(str(account_id),)).fetchone()
                    if existing:
                        if existing[0] not in fingerprints:
                            raise RuntimeError("Proxy vinculado à conta não está mais na lista; reconfigure o vínculo antes de publicar")
                        proxy_hash = existing[0]
                    else:
                        used = {row[0] for row in connection.execute('SELECT proxy_hash FROM assignments')}
                        proxy_hash = next((key for key in fingerprints if key not in used), None)
                        if proxy_hash is None:
                            raise RuntimeError("Não há proxy livre para esta conta")
                        connection.execute('INSERT INTO assignments(account,proxy_hash) VALUES(?,?)',(str(account_id),proxy_hash))
                    connection.commit()
                    return fingerprints[proxy_hash]
                finally:
                    connection.close()
            except sqlite3.Error:
                raise RuntimeError("Não foi possível acessar os vínculos de proxies; publicação não enviada") from None

    def connection_failed(self, proxy: str) -> None:
        """Failures keep the account's assignment; existing retries use it again."""
        return


publication_proxy_pool = PublicationProxyPool()
