"""Import host:port:user:password lists without printing credentials.

This tool only edits the specified dotenv file; it never contacts a proxy/Meta
and never starts or restarts services. Use --check-only to validate the input.
"""
import argparse
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import quote, urlsplit


def parse_proxy_list(text: str) -> list[str]:
    proxies = []
    for index, entry in enumerate(text.split(), 1):
        try:
            host, port_text, username, password = entry.split(":", 3)
            port = int(port_text)
            if not host or not username or not password or not 1 <= port <= 65535:
                raise ValueError
            if any(char in host for char in "/@?#\\"):
                raise ValueError
            url = f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}"
            parsed = urlsplit(url)
            if parsed.hostname != host.lower() or parsed.port != port:
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError(f"Formato inválido na entrada {index}; esperado host:porta:usuario:senha") from None
        if url not in proxies:
            proxies.append(url)
    if not proxies:
        raise ValueError("A lista de proxies está vazia")
    return proxies


def update_dotenv(text: str, proxies: list[str], block_size: int) -> str:
    if block_size < 1:
        raise ValueError("O bloco deve ser positivo")
    values = {
        "META_PUBLISH_PROXY_URL": "",
        "META_PUBLISH_PROXY_URLS": "'" + json.dumps(proxies, ensure_ascii=True, separators=(",", ":")) + "'",
        "META_PUBLISH_PROXY_POSTS_PER_PROXY": str(block_size),
    }
    newline = "\r\n" if "\r\n" in text else "\n"
    result, seen = [], set()
    for line in text.splitlines(keepends=True):
        match = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=", line)
        name = match.group(1) if match else None
        if name in values:
            if name not in seen:
                result.append(f"{name}={values[name]}{newline}")
                seen.add(name)
        else:
            result.append(line)
    if result and not result[-1].endswith(("\n", "\r")):
        result[-1] += newline
    result.extend(f"{name}={value}{newline}" for name, value in values.items() if name not in seen)
    return "".join(result)


def write_dotenv(path: Path, text: str) -> None:
    original = path.stat()
    fd, temporary = tempfile.mkstemp(prefix=".proxy-env-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        if hasattr(os, "chown"):
            os.chown(temporary, original.st_uid, original.st_gid)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--env", type=Path)
    parser.add_argument("--block-size", type=int, default=10)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    try:
        proxies = parse_proxy_list(args.input.read_text(encoding="utf-8-sig"))
        if args.block_size < 1:
            raise ValueError("O bloco deve ser positivo")
        if not args.check_only:
            if args.env is None:
                raise ValueError("Informe --env ou use --check-only")
            with args.env.open(encoding="utf-8", newline="") as stream:
                current = stream.read()
            write_dotenv(args.env, update_dotenv(current, proxies, args.block_size))
        print(f"Proxies únicos: {len(proxies)}; bloco: {args.block_size}; "
              f"modo: {'validação' if args.check_only else 'configurado'}")
    except (ValueError, OSError) as error:
        # OSError may mention paths, but no input lines/credentials are printed.
        parser.exit(1, f"Falha: {error}\n")


if __name__ == "__main__":
    main()
