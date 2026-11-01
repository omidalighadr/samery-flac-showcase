"""Convert verified ALAC to FLAC without resampling or increasing bit depth."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess


def probe(path: Path, ffprobe: str) -> dict:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        check=True,
        timeout=30,
    )
    return json.loads(result.stdout)["streams"][0]


def pcm_hash(path: Path, ffmpeg: str) -> bytes:
    result = subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-c:a",
            "pcm_s32le",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "pipe:1",
        ],
        capture_output=True,
        check=True,
        timeout=180,
    )
    return result.stdout.strip()


def to_flac(path: Path, ffmpeg: str, ffprobe: str) -> tuple[Path, dict]:
    source = probe(path, ffprobe)
    if source.get("codec_name") != "alac":
        raise ValueError("Lossy input rejected")
    bits = int(source.get("bits_per_raw_sample") or source.get("bits_per_sample") or 0)
    if bits not in (16, 24):
        raise ValueError("Unsupported source bit depth")
    destination = path.with_suffix(".flac")
    try:
        subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(path),
                "-map",
                "0:a:0",
                "-map_metadata",
                "0",
                "-c:a",
                "flac",
                "-compression_level",
                "12",
                str(destination),
            ],
            capture_output=True,
            check=True,
            timeout=180,
        )
        result = probe(destination, ffprobe)
        output_bits = int(result.get("bits_per_raw_sample") or result.get("bits_per_sample") or 0)
        if (
            result.get("codec_name") != "flac"
            or output_bits != bits
            or result["sample_rate"] != source["sample_rate"]
            or result["channels"] != source["channels"]
            or pcm_hash(path, ffmpeg) != pcm_hash(destination, ffmpeg)
        ):
            raise ValueError("Lossless verification failed")
        # FFmpeg copies text tags; keep the original embedded artwork too.
        from mutagen.mp4 import MP4
        from mutagen.flac import FLAC, Picture

        mp4 = MP4(path)
        flac = FLAC(destination)
        for atom, tag in (("\xa9lyr", "lyrics"), ("cnID", "apple_music_id"), ("\xa9day", "date")):
            if value := (mp4.tags or {}).get(atom):
                flac[tag] = str(value[0])
        for cover in (mp4.tags or {}).get("covr", []):
            picture = Picture()
            picture.type = 3
            picture.mime = "image/png" if bytes(cover).startswith(b"\x89PNG") else "image/jpeg"
            picture.data = bytes(cover)
            flac.add_picture(picture)
        flac.save()
        return destination, dict(bit_depth=bits, sample_rate=int(result["sample_rate"]))
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
