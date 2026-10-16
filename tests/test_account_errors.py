import json
import unittest
from app.account_errors import account_access_failed


def error(code, subcode=0, transient=False, message="Synthetic", **extra):
    return RuntimeError("Meta: " + json.dumps({"error": {"type": "OAuthException", "code": code,
        "error_subcode": subcode, "is_transient": transient, "message": message, **extra}}))


class AccountErrorTests(unittest.TestCase):
    def test_media_creation_does_not_disable_account(self):
        self.assertFalse(account_access_failed(error(-1,2207032,message="Cannot Create Media")))
    def test_transient_oauth_does_not_disable_account(self):
        self.assertFalse(account_access_failed(error(2,transient=True)))
        self.assertFalse(account_access_failed(error(190,transient=True)))
    def test_invalid_token_and_session_disable(self):
        self.assertTrue(account_access_failed(error(190,463)))
        self.assertTrue(account_access_failed(error(102)))
    def test_permission_is_scoped_to_verification(self):
        self.assertFalse(account_access_failed(error(200)))
        self.assertTrue(account_access_failed(error(200),verification=True))
    def test_general_request_failures_are_not_account_failures(self):
        for text in ("HTTP 401 proxy", "403 proxy denied", "container EXPIRED", "OAuthException", "Unsupported post request", "permission for media", "timeout"):
            with self.subTest(text=text): self.assertFalse(account_access_failed(RuntimeError(text)))
    def test_truncated_json_can_preserve_known_token_code(self):
        self.assertTrue(account_access_failed(RuntimeError('Meta: {"error":{"code":190,"message":"truncated')))
        self.assertFalse(account_access_failed(RuntimeError('Meta: {"error":{"code":190,"is_transient":true,"message":"truncated')))
    def test_wrapped_exception_detail(self):
        e=RuntimeError("generic");e.detail=str(error(190))
        self.assertTrue(account_access_failed(e))


if __name__=="__main__": unittest.main()
