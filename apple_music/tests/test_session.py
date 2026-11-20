"""Synthetic account-bootstrap tests; no real cookies or tokens."""
import asyncio
from contextlib import contextmanager
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import apple_session as session


@contextmanager
def responses(responder):
    original = httpx.AsyncClient
    options = []

    def factory(**kwargs):
        options.append(kwargs)
        return original(transport=httpx.MockTransport(responder), **kwargs)

    async def no_sleep(seconds):
        return None

    with patch.object(session.httpx, "AsyncClient", factory):
        with patch.object(session.asyncio, "sleep", no_sleep):
            yield options


class SessionTests(unittest.TestCase):
    def test_transient_timeout_is_retried(self):
        requests = []

        def respond(request):
            requests.append(request)
            if len(requests) == 1:
                raise httpx.ReadTimeout("synthetic", request=request)
            return httpx.Response(200, json={"meta": {"subscription": {"active": True}}})

        with responses(respond) as options:
            result = asyncio.run(session.resilient_api(object).get_account_info("synthetic-dev", "synthetic-user"))
        self.assertTrue(result["meta"]["subscription"]["active"])
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(o["timeout"].read == 45 and o["timeout"].connect == 30 for o in options))

    def test_rejected_account_does_not_leak_response(self):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(403, text="synthetic-sensitive-response")

        with responses(respond):
            with self.assertRaises(session.AppleSessionError) as caught:
                asyncio.run(session.fetch(session.ACCOUNT, headers={"cookie": "synthetic-user"}))
        self.assertEqual(str(caught.exception), "account_rejected")
        self.assertEqual(len(requests), 1)

    def test_network_retry_budget_is_three_attempts(self):
        requests = []

        def respond(request):
            requests.append(request)
            raise httpx.ConnectTimeout("synthetic-sensitive-response", request=request)

        with responses(respond):
            with self.assertRaises(session.AppleSessionError) as caught:
                asyncio.run(session.fetch(session.ACCOUNT))
        self.assertEqual(str(caught.exception), "network")
        self.assertEqual(len(requests), 3)

    def test_account_credentials_do_not_follow_redirects(self):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(302, headers={"location": "https://other.example/"})

        with responses(respond):
            with self.assertRaises(session.AppleSessionError):
                asyncio.run(session.fetch(session.ACCOUNT, headers={"cookie": "synthetic-user"}))
        self.assertEqual(len(requests), 1)

    def test_token_discovery_reads_only_public_apple_asset(self):
        requests = []

        def respond(request):
            requests.append(request)
            text = '<script src="/assets/index~test.js"></script>' if len(requests) == 1 else '"eyJabc.eyJdef.test"'
            return httpx.Response(200, text=text)

        with responses(respond):
            token = asyncio.run(session.resilient_api(object).get_token())
        self.assertEqual(token, "eyJabc.eyJdef.test")
        self.assertEqual(str(requests[1].url), "https://music.apple.com/assets/index~test.js")
        self.assertNotIn("cookie", requests[1].headers)


if __name__ == "__main__":
    unittest.main()
