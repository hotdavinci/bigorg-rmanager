"""Synthetic transport tests: never load real settings or contact Meta."""
import ast
import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
from types import SimpleNamespace
import unittest
import tempfile
from unittest.mock import patch

import httpx
from app.publish_proxy import PublicationProxyPool


class PublishProxyTests(unittest.IsolatedAsyncioTestCase):
    async def run_publication(self, proxy="", fail=False):
        source = Path(__file__).resolve().parents[1] / "app/meta.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        functions = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                     and node.name in {"publish_reel", "_publish_reel"}]
        settings = SimpleNamespace(meta_graph_api_version="25.0",
            meta_graph_base_url="https://graph.example",
            meta_publish_proxy_url=SimpleNamespace(get_secret_value=lambda: proxy))
        settings.meta_publish_proxy_urls=SimpleNamespace(get_secret_value=lambda: "")
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        settings.data_dir=Path(temporary.name)
        namespace = dict(httpx=httpx, asyncio=asyncio,
                         AsyncExitStack=AsyncExitStack, settings=settings,
                         publication_proxy_pool=PublicationProxyPool())
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)
        calls, clients = [], []
        real_client = httpx.AsyncClient

        def make_client(**kwargs):
            clients.append(kwargs)
            route = "proxy" if kwargs.get("proxy") else "direct"

            def respond(request):
                calls.append((route, request.method, request.url.path))
                if fail:
                    raise httpx.ProxyError("http://secret:password@proxy.example")
                if request.method == "GET":
                    return httpx.Response(200, json={"status_code": "FINISHED"})
                return httpx.Response(200, json={"id": "published" if request.url.path.endswith("media_publish") else "container"})

            return real_client(transport=httpx.MockTransport(respond), trust_env=False)

        with patch.object(httpx, "AsyncClient", side_effect=make_client):
            result = await namespace["publish_reel"]("account", "synthetic-token",
                "https://media.example/media/synthetic", "caption", "")
        return result, calls, clients

    async def test_only_posts_use_proxy_even_with_ambient_proxy(self):
        with patch.dict("os.environ", {"HTTPS_PROXY": "http://ambient.invalid:8080"}):
            result, calls, clients = await self.run_publication("http://user:password@proxy.example:8080")
        self.assertEqual(result, "published")
        self.assertEqual([item[:2] for item in calls],
                         [("proxy", "POST"), ("direct", "GET"), ("proxy", "POST")])
        self.assertTrue(all(client["trust_env"] is False for client in clients))

    async def test_empty_proxy_keeps_all_calls_direct(self):
        _, calls, clients = await self.run_publication()
        self.assertEqual(len(clients), 1)
        self.assertTrue(all(route == "direct" for route, _, _ in calls))

    async def test_invalid_proxy_does_not_fall_back_to_direct(self):
        with self.assertRaisesRegex(RuntimeError, "Proxy inválido"):
            await self.run_publication("socks5://user:password@proxy.example:1080")

    async def test_transport_errors_do_not_expose_proxy_credentials(self):
        with self.assertRaises(RuntimeError) as caught:
            await self.run_publication("http://user:password@proxy.example:8080", fail=True)
        self.assertNotIn("password", str(caught.exception))
        self.assertNotIn("proxy.example", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
