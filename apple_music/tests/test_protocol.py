import asyncio
import struct
import socket
import pytest
from scripts import apple_legacy as legacy
_connect = socket.socket.connect


def batch(adam, uri, samples):
    return (
        struct.pack(">HHI", len(adam), len(uri), len(samples))
        + b"".join(struct.pack(">I", len(s)) for s in samples)
        + adam
        + uri
        + b"".join(samples)
    )

@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"\x00" * 8,
        batch(b"12", b"skd://test", [b"hello"])[:-1],
        batch(b"12", b"skd://test", [b"hello"]) + b"extra",
        batch(b"x", b"skd://test", [b"hello"]),
        batch(b"12", b"https://test", [b"hello"]),
        batch(b"12", b"skd://test", [b""]),
    ],
)
def test_invalid_frames_rejected(body):
    with pytest.raises(ValueError):
        legacy.parse_batch(body)

def test_translation_batches_key_changes_and_partial_reads(monkeypatch):
    def loopback_only(sock, address):
        assert address[0] == "127.0.0.1"
        return _connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", loopback_only)

    async def run():
        identities = []
        finished = asyncio.Event()

        async def daemon(reader, writer):
            try:
                while True:
                    adam = await reader.readexactly((await reader.readexactly(1))[0])
                    uri = await reader.readexactly((await reader.readexactly(1))[0])
                    identities.append((adam, uri))
                    while True:
                        size = struct.unpack("<I", await reader.readexactly(4))[0]
                        if not size:
                            break
                        sample = await reader.readexactly(size)
                        plain = bytes(b ^ 0x55 for b in sample)
                        for chunk in (plain[:1], plain[1:]):
                            writer.write(chunk)
                            await writer.drain()
                            await asyncio.sleep(0)
            except asyncio.IncompleteReadError:
                pass
            finally:
                writer.close()
                await writer.wait_closed()
                finished.set()

        try:
            server = await asyncio.start_server(daemon, "127.0.0.1", 0)
        except PermissionError:
            pytest.skip("This environment does not permit loopback socket listeners")
        wrapper = await legacy.LegacyWrapper(
            None, legacy_port=server.sockets[0].getsockname()[1]
        ).start()
        reader, writer = await asyncio.open_connection("127.0.0.1", wrapper.decrypt_port)
        try:
            for request_id, uri in enumerate((b"skd://first", b"skd://first", b"skd://second")):
                samples = [b"abc", b"d" * 131072]
                payload = batch(b"123", uri, samples)
                writer.write(legacy.HEADER.pack(b"WV2D", 1, 1, request_id, len(payload)) + payload)
                await writer.drain()
                header = legacy.HEADER.unpack(await reader.readexactly(16))
                assert header[:4] == (b"WV2D", 1, 2, request_id)
                body = await reader.readexactly(header[4])
                expected = struct.pack(">III", 2, 3, 131072)
                expected += bytes(b ^ 0x55 for b in b"".join(samples))
                assert body == expected
            writer.write(legacy.HEADER.pack(b"WV2D", 1, 9, 99, 0))
            await writer.drain()
            assert await reader.read() == b""
            await asyncio.wait_for(finished.wait(), 2)
            assert identities == [(b"123", b"skd://first"), (b"123", b"skd://second")]
        finally:
            writer.close()
            await writer.wait_closed()
            await wrapper.aclose()
            server.close()
            await server.wait_closed()

    asyncio.run(asyncio.wait_for(run(), 10))
