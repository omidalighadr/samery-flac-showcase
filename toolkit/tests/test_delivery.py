import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import send_flac


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "sample.flac"
        self.path.write_bytes(b"test fixture")
        self.token = "123456:TEST_ONLY_NOT_A_REAL_TOKEN"

    def test_invalid_token_never_connects(self):
        with patch("http.client.HTTPSConnection") as connection:
            with self.assertRaises(send_flac.DeliveryError):
                send_flac.send(self.path, "", "123")
            connection.assert_not_called()

    def test_large_file_stays_local(self):
        with self.path.open("wb") as output:
            output.truncate(send_flac.LIMIT)
        with patch("http.client.HTTPSConnection") as connection:
            with self.assertRaises(send_flac.DeliveryError):
                send_flac.send(self.path, self.token, "123")
            connection.assert_not_called()
        self.assertTrue(self.path.exists())

    def run_delivery(self, *, uncertain=False, success=True):
        response = MagicMock(status=200)
        response.read.return_value = json.dumps({
            "ok": success,
            "result": {"message_id": 42, "document": {"file_size": self.path.stat().st_size}},
        }).encode()
        with patch.object(send_flac, "probe", return_value=MagicMock(codec="flac")), patch.object(send_flac, "pcm_sha256"), patch("http.client.HTTPSConnection") as factory:
            connection = factory.return_value
            if uncertain:
                connection.getresponse.side_effect = TimeoutError("secret request URL")
            else:
                connection.getresponse.return_value = response
            if success and not uncertain:
                self.assertEqual(send_flac.send(self.path, self.token, "123"), 42)
            else:
                with self.assertRaises(send_flac.DeliveryError) as error:
                    send_flac.send(self.path, self.token, "123")
                self.assertNotIn("secret request", str(error.exception))
            self.assertEqual(connection.putrequest.call_count, 1)
            connection.close.assert_called_once()
        self.assertTrue(self.path.exists())

    def test_confirmed_delivery_keeps_original(self):
        self.run_delivery()

    def test_uncertain_delivery_is_not_retried(self):
        self.run_delivery(uncertain=True)

    def test_rejected_delivery_keeps_original(self):
        self.run_delivery(success=False)
