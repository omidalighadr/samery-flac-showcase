"""Compare decoded integer PCM in local lossless audio files using FFmpeg."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

__version__ = "0.1.0"
SUPPORTED_CODECS = {
    "alac",
    "flac",
    "pcm_s16le",
    "pcm_s16be",
    "pcm_s24le",
    "pcm_s24be",
    "pcm_s32le",
    "pcm_s32be",
}


class VerificationError(Exception):
    """A file cannot be verified within the supported integer PCM contract."""


@dataclass(frozen=True)
class AudioInfo:
    codec: str
    sample_rate: int
    channels: int
    bit_depth: int
    channel_layout: str


@dataclass(frozen=True)
class Comparison:
    equivalent: bool
    source: AudioInfo
    candidate: AudioInfo
    source_sha256: str
    candidate_sha256: str
    differences: tuple[str, ...]


def _run(command: list[str], timeout: float) -> str:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError as exc:
        raise VerificationError(
            "FFmpeg and FFprobe must be installed and available."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise VerificationError("Audio verification timed out.") from exc
    if result.returncode:
        # Decoder stderr may contain paths or metadata; do not echo it by default.
        raise VerificationError(
            "FFmpeg could not probe or decode the local audio file."
        )
    return result.stdout


def _local_file(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise VerificationError("Both inputs must be existing local files.")
    return path


def probe(
    path: str | Path, *, ffprobe: str = "ffprobe", timeout: float = 300
) -> AudioInfo:
    """Inspect the first audio stream; reject lossy and floating-point codecs."""
    path = _local_file(path)
    raw = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-select_streams",
            "a:0",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        timeout,
    )
    try:
        stream = json.loads(raw)["streams"][0]
        codec = stream["codec_name"]
        rate = int(stream["sample_rate"])
        channels = int(stream["channels"])
        bits = int(
            stream.get("bits_per_raw_sample") or stream.get("bits_per_sample") or 0
        )
        layout = stream.get("channel_layout") or (
            {1: "mono", 2: "stereo"}.get(channels, "unknown")
        )
    except (KeyError, IndexError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise VerificationError("Audio stream metadata is incomplete.") from exc
    if (
        codec not in SUPPORTED_CODECS
        or bits not in (16, 24, 32)
        or rate <= 0
        or channels <= 0
    ):
        raise VerificationError(
            "Supported inputs are lossless integer ALAC, FLAC or PCM with 16, 24 or 32 bits."
        )
    if channels > 2 and layout == "unknown":
        raise VerificationError(
            "Multichannel audio requires an explicit channel layout."
        )
    return AudioInfo(codec, rate, channels, bits, layout)


def pcm_sha256(
    path: str | Path, *, ffmpeg: str = "ffmpeg", timeout: float = 300
) -> str:
    """Hash signed 32-bit little-endian decoded PCM, without resampling or downmixing.

    FFmpeg's hash muxer computes the digest incrementally, so Python does not
    accumulate decoded audio in memory. Call probe() first to validate the codec.
    """
    path = _local_file(path)
    raw = _run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-xerror",
            "-err_detect",
            "explode",
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-c:a",
            "pcm_s32le",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "-",
        ],
        timeout,
    )
    match = re.fullmatch(r"SHA256=([0-9a-fA-F]{64})\s*", raw)
    if not match:
        raise VerificationError("Unexpected FFmpeg digest output.")
    return match[1].lower()


def compare(
    source: str | Path,
    candidate: str | Path,
    *,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    timeout: float = 300,
) -> Comparison:
    """Require matching format properties AND identical decoded audio samples."""
    if timeout <= 0:
        raise VerificationError("Timeout must be positive.")
    source, candidate = _local_file(source), _local_file(candidate)

    def fingerprint(path):
        info = path.stat()
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns

    initial = fingerprint(source), fingerprint(candidate)
    first = probe(source, ffprobe=ffprobe, timeout=timeout)
    second = probe(candidate, ffprobe=ffprobe, timeout=timeout)
    differences = [
        field
        for field in ("sample_rate", "channels", "bit_depth", "channel_layout")
        if getattr(first, field) != getattr(second, field)
    ]
    first_hash = pcm_sha256(source, ffmpeg=ffmpeg, timeout=timeout)
    second_hash = pcm_sha256(candidate, ffmpeg=ffmpeg, timeout=timeout)
    if initial != (fingerprint(source), fingerprint(candidate)):
        raise VerificationError(
            "An input changed during verification; retry with stable files."
        )
    if first_hash != second_hash:
        differences.append("decoded_pcm")
    return Comparison(
        not differences, first, second, first_hash, second_hash, tuple(differences)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument(
        "--timeout",
        type=float,
        default=300,
        help="Maximum seconds per subprocess (default: 300)",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit a machine-readable report"
    )
    args = parser.parse_args(argv)
    try:
        result = compare(args.source, args.candidate, timeout=args.timeout)
    except (VerificationError, OSError) as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}))
        else:
            print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(asdict(result), indent=2))
    else:
        print(
            "PASS: matching decoded PCM and format properties."
            if result.equivalent
            else "FAIL: differences in " + ", ".join(result.differences)
        )
    return 0 if result.equivalent else 1


if __name__ == "__main__":
    raise SystemExit(main())
