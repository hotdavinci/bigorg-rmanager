import json
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import unittest
import tempfile
from pathlib import Path

from app.publish_proxy import PublicationProxyPool
from tools.configure_publish_proxies import parse_proxy_list, update_dotenv


class ProxyPoolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.database=Path(self.temp.name)/"assignments.sqlite3"
        self.urls=["http://user:synthetic@one.example:8080","http://user:synthetic@two.example:8080"]
        self.pool=PublicationProxyPool()

    def tearDown(self):
        self.temp.cleanup()

    def select(self,account,pool=None,urls=None):
        return (pool or self.pool).for_account(account,json.dumps(urls or self.urls),"",self.database)

    def test_same_proxy_after_many_posts_and_restart(self):
        first=self.select("account-a")
        for _ in range(25):self.assertEqual(self.select("account-a"),first)
        self.assertEqual(self.select("account-a",PublicationProxyPool()),first)

    def test_different_accounts_have_different_proxies(self):
        self.assertNotEqual(self.select("a"),self.select("b"))

    def test_concurrent_reservations_are_unique_across_pool_instances(self):
        urls=[f"http://proxy{i}.example:8080" for i in range(8)]
        with ThreadPoolExecutor(max_workers=8) as executor:
            chosen=list(executor.map(lambda i:self.select(str(i),PublicationProxyPool(),urls),range(8)))
        self.assertEqual(len(set(chosen)),8)

    def test_reordering_does_not_change_assignment(self):
        first=self.select("a")
        self.assertEqual(self.select("a",urls=list(reversed(self.urls))),first)

    def test_failure_does_not_rotate_assignment(self):
        first=self.select("a");self.pool.connection_failed(first)
        self.assertEqual(self.select("a"),first)

    def test_removed_proxy_fails_without_direct_fallback(self):
        first=self.select("a")
        with self.assertRaisesRegex(RuntimeError,"Proxy vinculado"):
            self.select("a",urls=[u for u in self.urls if u!=first])

    def test_exhausted_pool_does_not_share_proxy(self):
        self.select("a");self.select("b")
        with self.assertRaisesRegex(RuntimeError,"proxy livre"):self.select("c")

    def test_invalid_pool_does_not_expose_credentials(self):
        with self.assertRaises(RuntimeError) as error:
            self.pool.for_account("a",'["socks5://user:password@proxy.example:80"]',"",self.database)
        self.assertNotIn("password",str(error.exception))


class ProxyImportTests(unittest.TestCase):
    def test_parse_deduplicates_and_encodes_credentials(self):
        urls = parse_proxy_list("proxy.example:8080:user@name:pass:#word\nproxy.example:8080:user@name:pass:#word")
        self.assertEqual(urls, ["http://user%40name:pass%3A%23word@proxy.example:8080"])

    def test_invalid_input_reports_position_without_credentials(self):
        with self.assertRaises(ValueError) as caught:
            parse_proxy_list("proxy.example:8080:user:synthetic\nbad:port:secret:password")
        self.assertIn("entrada 2", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))

    def test_env_preserves_unrelated_settings_and_replaces_duplicates(self):
        text = "# synthetic\r\nAPP_ENCRYPTION_KEY=synthetic-key\r\nMETA_PUBLISH_PROXY_URL=old\r\nMETA_PUBLISH_PROXY_URL=duplicate\r\nOTHER=untouched"
        result = update_dotenv(text, ["http://user:synthetic@proxy.example:8080"], 10)
        self.assertIn("APP_ENCRYPTION_KEY=synthetic-key\r\n", result)
        self.assertIn("OTHER=untouched\r\n", result)
        self.assertEqual(result.count("META_PUBLISH_PROXY_URL="), 1)
        self.assertIn("META_PUBLISH_PROXY_POSTS_PER_PROXY=10\r\n", result)


if __name__ == "__main__":
    unittest.main()
