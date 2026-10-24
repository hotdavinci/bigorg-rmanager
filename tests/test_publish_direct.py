"""Synthetic Meta transport test; no real credentials or external requests."""
import ast
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx


class PublishDirectTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_publication_requests_are_direct(self):
        source = Path(__file__).resolve().parents[1] / "app/meta.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        functions = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                     and node.name in {"publish_reel", "_publish_reel"}]
        namespace = dict(httpx=httpx, asyncio=asyncio,
                         settings=SimpleNamespace(meta_graph_api_version="25.0",
                                                  meta_graph_base_url="https://graph.example"))
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)
        clients, calls = [], []
        real_client = httpx.AsyncClient

        def make_client(**kwargs):
            clients.append(kwargs)
            def respond(request):
                calls.append(request.method)
                if request.method == "GET":
                    return httpx.Response(200, json={"status_code": "FINISHED"})
                return httpx.Response(200, json={"id": "published" if request.url.path.endswith("media_publish") else "container"})
            return real_client(transport=httpx.MockTransport(respond), trust_env=False)

        with patch.dict("os.environ", {"HTTPS_PROXY": "http://ambient.invalid:8080"}):
            with patch.object(httpx, "AsyncClient", side_effect=make_client):
                result = await namespace["publish_reel"]("account", "synthetic-token",
                    "https://media.example/synthetic", "caption")
        self.assertEqual(result, "published")
        self.assertEqual(calls, ["POST", "GET", "POST"])
        self.assertEqual(len(clients), 1)
        self.assertFalse(clients[0]["trust_env"])
        self.assertNotIn("proxy", clients[0])


if __name__ == "__main__":
    unittest.main()
