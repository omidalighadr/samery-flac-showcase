import asyncio
import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import bot as public_bot


@pytest.mark.parametrize("url", [
    "https://music.apple.com.evil.test/us/song/a/123",
    "https://music.apple.com@evil.test/us/song/a/123",
    "https://music.apple.com/us/album/a/123?i=wrong",
    "https://example.com/us/song/a/123",
    "https://music.apple.com/us/song/a/123 https://music.apple.com/us/song/a/456",
])
def test_bad_links_rejected(url):
    assert not public_bot.apple_url(url)


def test_track_url_keeps_identity_and_removes_tracking():
    assert public_bot.apple_url("/apple https://music.apple.com/us/album/a/123?i=456&source=tracking") == "https://music.apple.com/us/album/a/123?i=456"


def test_unconfigured_bot_fails_closed(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(ValueError):
        public_bot.Settings.from_env()


def test_external_worker_output_rejected(tmp_path):
    outside = tmp_path / "outside.flac"
    outside.write_bytes(b"fixture")
    job = tmp_path / "job"
    job.mkdir()
    with pytest.raises(ValueError):
        public_bot.managed_file(outside, job)
    link = job / "linked.flac"
    link.symlink_to(outside)
    with pytest.raises(ValueError):
        public_bot.managed_file(link, job)


def test_delivery_timeout_does_not_retry_or_delete(tmp_path):
    path = tmp_path / "track.flac"
    path.write_bytes(b"fixture")
    telegram = NS(send_document=AsyncMock(side_effect=TimeoutError("private details")))
    with patch.object(public_bot, "metadata", return_value={"format":"FLAC", "duration":10}), patch.object(public_bot, "thumbnail", return_value=None), patch.object(public_bot, "filename", return_value="Artist - Track.flac"):
        with pytest.raises(TimeoutError):
            asyncio.run(public_bot.deliver(telegram, 123, path, {}))
    assert telegram.send_document.await_count == 1
    assert path.exists()


@pytest.mark.parametrize("correct", [True, False])
def test_delivery_checks_returned_size(tmp_path, correct):
    path = tmp_path / "track.flac"
    path.write_bytes(b"fixture")
    telegram = NS(send_document=AsyncMock(return_value=NS(document=NS(file_id="fixture",file_size=path.stat().st_size if correct else 1))))
    with patch.object(public_bot, "metadata", return_value={"format":"FLAC", "duration":10}), patch.object(public_bot, "thumbnail", return_value=None), patch.object(public_bot, "filename", return_value="Artist - Track.flac"):
        if correct:
            asyncio.run(public_bot.deliver(telegram, 123, path, {}))
        else:
            with pytest.raises(ValueError):
                asyncio.run(public_bot.deliver(telegram, 123, path, {}))
    assert path.exists()


@pytest.mark.parametrize("mode", ["sent", "uncertain", "large"])
def test_worker_acknowledged_only_after_delivery_or_verified_copy(tmp_path, mode):
    settings = public_bot.Settings("synthetic", frozenset({123}), tmp_path / "cookies.txt", tmp_path, "http://127.0.0.1:10020")
    stdin = MagicMock()
    stdin.drain = AsyncMock()
    created = []

    async def factory(*argv, **kwargs):
        directory = Path(argv[argv.index("--output")+1])
        path = directory / "track.flac"
        path.write_bytes(b"synthetic bytes")
        created.append(path)
        reader = asyncio.StreamReader()
        reader.feed_data((json.dumps({"event":"track", "path":str(path), "title":"Synthetic track", "format":"FLAC"})+"\n").encode())
        reader.feed_data(b'{"event":"done"}\n')
        reader.feed_eof()
        assert "TELEGRAM_BOT_TOKEN" not in kwargs["env"]
        return NS(stdout=reader, stdin=stdin, returncode=0, wait=AsyncMock(return_value=0))

    send = AsyncMock(side_effect=TimeoutError() if mode == "uncertain" else None)
    with patch.object(public_bot.asyncio, "create_subprocess_exec", side_effect=factory), patch.object(public_bot, "stop_process", new_callable=AsyncMock), patch.object(public_bot, "deliver", send), patch.object(public_bot, "UPLOAD_LIMIT", 1 if mode == "large" else 50*1024*1024):
        coroutine = public_bot.run_job(settings, NS(send_message=AsyncMock()), 123, "https://music.apple.com/us/song/a/123", NS(edit_text=AsyncMock()))
        if mode == "uncertain":
            with pytest.raises(TimeoutError):
                asyncio.run(coroutine)
            stdin.write.assert_not_called()
            assert created[0].exists()
        else:
            asyncio.run(coroutine)
            stdin.write.assert_called_once_with(b"confirmed\n")
            assert not created[0].exists()
        if mode == "large":
            send.assert_not_awaited()
            retained = list((tmp_path / "retained").rglob("*.flac"))
            assert len(retained) == 1 and retained[0].read_bytes() == b"synthetic bytes"
