"""Run Samery's job and delivery path against generated audio, entirely offline."""

import argparse
import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

from bot import Settings, configure_logging, run_job
from scripts.apple_audio import to_flac


def generate_track(output: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("Install FFmpeg and FFprobe to run the offline demo.")
    source = output / "generated-tone.m4a"
    subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi", "-i",
         "sine=frequency=440:sample_rate=44100:duration=1", "-c:a", "alac", str(source)],
        check=True,
    )
    path, quality = to_flac(source, ffmpeg, ffprobe)
    print(json.dumps({
        "event": "track",
        "path": str(path),
        "title": "Generated tone",
        "artist": "Samery offline demo",
        "format": "FLAC",
        **quality,
    }), flush=True)
    if sys.stdin.readline().strip() != "confirmed":
        raise RuntimeError("The simulated delivery was not confirmed.")
    print(json.dumps({"event": "done"}), flush=True)


class LocalReceiver:
    def __init__(self) -> None:
        self.received = 0

    async def send_document(self, chat_id, *, document, filename, **kwargs):
        data = document.read()
        if not data.startswith(b"fLaC"):
            raise ValueError("Expected a FLAC document.")
        self.received += 1
        print(f"Simulated Telegram receipt: {filename} ({len(data)} bytes)")
        return SimpleNamespace(document=SimpleNamespace(
            file_id="offline-demo", file_size=len(data),
        ))


class ConsoleStatus:
    async def edit_text(self, text):
        print(text)


async def demo() -> None:
    configure_logging()
    print("Offline demo: generated tone, real FLAC conversion, simulated Telegram receipt.")
    with tempfile.TemporaryDirectory(prefix="samery-offline-demo-") as temporary:
        data = Path(temporary)
        receiver = LocalReceiver()
        settings = Settings("", frozenset({1}), data / "unused", data, "")
        await run_job(settings, receiver, 1, "", ConsoleStatus(), worker_script=Path(__file__).resolve())
        if receiver.received != 1 or any((data / "jobs").iterdir()):
            raise RuntimeError("Offline demo did not finish with a confirmed receipt and clean job directory.")
    print("PASS: PCM verified, delivery acknowledged, working files cleaned up.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help=argparse.SUPPRESS)
    args, extra = parser.parse_known_args()
    if args.output:
        generate_track(args.output)
    elif extra:
        parser.error("unrecognized arguments: " + " ".join(extra))
    else:
        asyncio.run(demo())
