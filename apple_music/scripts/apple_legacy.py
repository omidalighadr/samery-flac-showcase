"""Loopback-only adapter for the published ARM Wrapper and gamdl's WV2D engine.

Protocol references: WorldObservationLog/wrapper main.c (ARM release) and
glomatico/wrapper-v2 src/rust/{protocol,main}.rs (0.0.2).
No account responses, signed URLs, key URIs or audio bytes are logged.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
import struct
from urllib.parse import urlsplit

HEADER = struct.Struct(">4sHHII")
MAX_FRAME = 32 * 1024 * 1024


def parse_batch(body: bytes):
    if len(body) < 8:
        raise ValueError("Invalid batch")
    adam_len, uri_len, count = struct.unpack_from(">HHI", body)
    if not 0 < adam_len <= 255 or not 0 < uri_len <= 255 or not 0 < count <= 65536:
        raise ValueError("Invalid batch fields")
    start = 8 + 4 * count
    offset = start + adam_len + uri_len
    if offset > len(body):
        raise ValueError("Truncated batch")
    lengths = struct.unpack_from(f">{count}I", body, 8)
    if any(n == 0 for n in lengths) or sum(lengths) + offset != len(body):
        raise ValueError("Invalid batch lengths")
    adam = body[start : start + adam_len]
    uri = body[start + adam_len : offset]
    if not adam.isdigit() or not uri.startswith(b"skd://"):
        raise ValueError("Invalid batch identity")
    samples = []
    for size in lengths:
        samples.append(body[offset : offset + size])
        offset += size
    return adam, uri, samples


class LegacyWrapper:
    def __init__(self, api, *, m3u8_port=20020, legacy_port=10020):
        self.api = api
        self.m3u8_port = m3u8_port
        self.legacy_port = legacy_port
        self.decrypt_host = "127.0.0.1"
        self.decrypt_port = 0
        self.server = None
        self.tasks = set()
        # The published legacy daemon handles one decrypt connection at a time.
        self.lock = asyncio.Lock()

    async def start(self):
        self.server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        self.decrypt_port = self.server.sockets[0].getsockname()[1]
        return self

    async def aclose(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def get_playback(self, media_id):
        adam = str(media_id).encode("ascii")
        if not adam.isdigit() or len(adam) > 255:
            raise ValueError("Invalid media identifier")
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", self.m3u8_port), 10
        )
        try:
            writer.write(bytes([len(adam)]) + adam)
            await writer.drain()
            raw = await asyncio.wait_for(reader.readline(), 90)
            url = raw.strip(b"\x00\r\n").decode("utf-8")
            parts = urlsplit(url)
            if (
                parts.scheme != "https"
                or not parts.hostname
                or not (
                    parts.hostname.endswith(".itunes.apple.com")
                    or parts.hostname.endswith(".music.apple.com")
                    or parts.hostname.endswith(".mzstatic.com")
                )
            ):
                raise ValueError("Wrapper did not return an Apple playlist")
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()
        playback = await self.api.get_webplayback(media_id, False)
        playback["songList"][0]["hls-playlist-url"] = url
        return playback

    async def _serve(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        legacy_writer = None
        request_id = 0
        try:
            async with self.lock:
                legacy_reader, legacy_writer = await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", self.legacy_port), 10
                )
                identity = None
                while True:
                    magic, version, kind, request_id, size = HEADER.unpack(
                        await asyncio.wait_for(reader.readexactly(HEADER.size), 90)
                    )
                    if magic != b"WV2D" or version != 1 or size > MAX_FRAME:
                        raise ValueError("Invalid decrypt frame")
                    if kind == 9 and size == 0:
                        break
                    if kind != 1:
                        raise ValueError("Unsupported decrypt frame")
                    body = await asyncio.wait_for(reader.readexactly(size), 90)
                    adam, uri, samples = parse_batch(body)
                    if identity != (adam, uri):
                        if identity:
                            legacy_writer.write(struct.pack("<I", 0))
                        legacy_writer.write(bytes([len(adam)]) + adam + bytes([len(uri)]) + uri)
                        identity = (adam, uri)
                    plaintexts = []
                    # Keep request/response alternating: the legacy server writes each
                    # sample before reading the next one, so batching can deadlock.
                    for sample in samples:
                        legacy_writer.write(struct.pack("<I", len(sample)) + sample)
                        await legacy_writer.drain()
                        plaintexts.append(
                            await asyncio.wait_for(legacy_reader.readexactly(len(sample)), 90)
                        )
                    payload = struct.pack(">I", len(samples))
                    payload += b"".join(struct.pack(">I", len(p)) for p in plaintexts)
                    payload += b"".join(plaintexts)
                    writer.write(HEADER.pack(b"WV2D", 1, 2, request_id, len(payload)) + payload)
                    await writer.drain()
        except (OSError, ValueError, asyncio.IncompleteReadError, TimeoutError):
            with suppress(OSError):
                message = b"Local Wrapper request failed"
                writer.write(HEADER.pack(b"WV2D", 1, 3, request_id, len(message)) + message)
                await writer.drain()
        finally:
            for stream in (legacy_writer, writer):
                if stream:
                    stream.close()
                    with suppress(OSError):
                        await stream.wait_closed()
            self.tasks.discard(task)
