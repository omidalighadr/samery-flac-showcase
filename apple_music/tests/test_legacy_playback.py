import importlib.util
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock, patch


path = Path(__file__).resolve().parents[1] / "scripts" / "apple_legacy.py"
spec = importlib.util.spec_from_file_location("apple_legacy", path)
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)


class LegacyPlaybackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.api = Mock(get_webplayback=AsyncMock(return_value={"songList": [{}]}))
        self.wrapper = legacy.LegacyWrapper(self.api)

    def mock_connections(self, *responses):
        writers = [
            Mock(drain=AsyncMock(), wait_closed=AsyncMock()) for _ in responses
        ]
        connections = [
            (Mock(readline=AsyncMock(return_value=response)), writer)
            for response, writer in zip(responses, writers)
        ]
        connect = AsyncMock(side_effect=connections)
        self.enterContext(patch.object(legacy.asyncio, "open_connection", connect))
        self.enterContext(patch.object(legacy, "PLAYBACK_RETRY_DELAY", 0))
        return connect, writers

    async def test_retries_invalid_urls_and_checks_account_after_valid_response(self):
        url = "https://audio.itunes.apple.com/example.m3u8"
        connect, writers = self.mock_connections(
            b"\n", b"https://example.test/rejected.m3u8\n", url.encode() + b"\n"
        )
        playback = await self.wrapper.get_playback("123")
        self.assertEqual(playback["songList"][0]["hls-playlist-url"], url)
        self.assertEqual(connect.await_count, 3)
        self.api.get_webplayback.assert_awaited_once_with("123", False)
        for writer in writers:
            writer.close.assert_called_once()

    async def test_stops_after_three_invalid_responses(self):
        connect, writers = self.mock_connections(b"\n", b"\n", b"\n")
        with self.assertRaisesRegex(ValueError, "did not return an Apple playlist"):
            await self.wrapper.get_playback("123")
        self.assertEqual(connect.await_count, 3)
        self.api.get_webplayback.assert_not_awaited()
        for writer in writers:
            writer.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
