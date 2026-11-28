"""Save verified Apple Music FLAC files locally using the bundled worker."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit, urlunsplit

from scripts.music_metadata import filename
from services import ordered_albums


ERROR_HINTS = {
    "account_rejected": "Apple rejected access. Check the Apple Music session and whether this track plays with the same account.",
    "subscription": "The Apple Music session has no active subscription.",
    "wrapper_unavailable": "Check that the configured playback service is running and that its backend matches the CLI settings.",
    "network": "Check your connection to Apple Music and retry.",
    "stream_network": "The audio stream could not be retrieved. Check your network and retry.",
    "apple_unavailable": "Apple Music is temporarily unavailable or rate limiting requests. Try again later.",
    "track_duration_mismatch": "The audio duration did not match the catalog. Retry the download.",
    "audio_decode_failed": "The downloaded audio could not be decoded. Retry the download.",
}


def catalog_url(value):
    parts = urlsplit(value)
    if parts.scheme != "https" or parts.netloc.lower() != "music.apple.com" or not re.fullmatch(
        r"/[a-zA-Z]{2}/(?:album|song|playlist)/(?:[^/]+/)?(?:[0-9]+|pl\.[\w-]+)", parts.path
    ):
        raise ValueError("Expected an Apple Music song, album or playlist URL.")
    song = parse_qs(parts.query).get("i", [""])[0]
    if song and ("/album/" not in parts.path or not song.isascii() or not song.isdigit()):
        raise ValueError("Invalid track ID.")
    return urlunsplit(("https", "music.apple.com", parts.path, f"i={song}" if song else "", ""))


def save_track(event, work, destination, *, ordered=False):
    raw = event.get("path")
    if not isinstance(raw, str) or not raw:
        raise ValueError("Worker produced an invalid output path.")
    source = Path(raw).resolve(strict=True)
    if not source.is_relative_to(Path(work).resolve(strict=True)) or not source.is_file() or source.suffix.lower() != ".flac":
        raise ValueError("Worker produced an invalid output path.")
    with ordered_albums.naming(ordered):
        public_name = ordered_albums.prefix(event) + filename(source, event)
    stem = Path(public_name).stem
    for index in range(1, 1001):
        name = public_name if index == 1 else f"{stem} ({index}){source.suffix}"
        target = destination / name
        try:
            os.link(source, target)
        except FileExistsError:
            continue
        return target
    raise ValueError("Too many files have the same name.")


def run(worker, url, destination, limit, *, lyrics=False):
    destination = destination.resolve()
    work = Path(tempfile.mkdtemp(prefix=".samery-", dir=destination)).resolve()
    confirmed = 0
    done = None
    error = False
    reported_codes = set()
    cmd = [sys.executable, "-B", str(worker), "--url", url, "--output", str(work),
           "--limit", str(limit), "--codec", "flac"]
    if lyrics:
        cmd.append("--lyrics")
    ordered = "/album/" in urlsplit(url).path and not parse_qs(urlsplit(url).query).get("i")
    cmd.extend(["--cookies", os.environ["APPLE_MUSIC_COOKIES"],
                "--wrapper", os.environ["APPLE_MUSIC_WRAPPER_URL"]])
    for option, env in (
        ("--wrapper-backend", "APPLE_MUSIC_WRAPPER_BACKEND"),
        ("--decrypt-host", "APPLE_MUSIC_DECRYPT_HOST"),
        ("--decrypt-port", "APPLE_MUSIC_DECRYPT_PORT"),
    ):
        if value := os.environ.get(env):
            cmd.extend([option, value])
    with subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True, encoding="utf-8") as process:
        try:
            for line in process.stdout:
                try:
                    event = json.loads(line)
                except ValueError:
                    raise ValueError("Invalid worker response.") from None
                if not isinstance(event, dict):
                    raise ValueError("Invalid worker response.")
                kind = event.get("event")
                if kind == "track":
                    target = save_track(event, work, destination, ordered=ordered)
                    process.stdin.write("saved\n")
                    process.stdin.flush()
                    confirmed += 1
                    print(f"Saved: {target.name!r}", flush=True)
                elif kind == "done":
                    done = event
                elif kind in ("error", "track_error"):
                    error = True
                    code = event.get("code")
                    if isinstance(code, str) and code in ERROR_HINTS and code not in reported_codes:
                        print(f"{code}: {ERROR_HINTS[code]}", file=sys.stderr)
                        reported_codes.add(code)
            returncode = process.wait()
        except BaseException:
            if process.poll() is None:
                process.kill()
            raise
    summary = done or {}
    count, failed = summary.get("count"), summary.get("failed")
    complete = type(count) is int and count == confirmed and type(failed) is int and failed == 0
    if returncode or error or not confirmed or not complete:
        print(f"Download incomplete. Saved {confirmed} file(s). Check {work.name} for unfinished files.",
              file=sys.stderr)
        return 1
    for folder in sorted((p for p in work.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        if not any(folder.iterdir()):
            folder.rmdir()
    if not any(work.iterdir()):
        work.rmdir()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--output", type=Path, default=Path("downloads"))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--lyrics", action="store_true", help="request available synchronized lyrics")
    args = parser.parse_args(argv)
    try:
        url = catalog_url(args.url)
        if not 1 <= args.limit <= 50:
            raise ValueError("Limit must be between 1 and 50.")
        if not Path(os.environ.get("APPLE_MUSIC_COOKIES", "")).is_file() or not os.environ.get("APPLE_MUSIC_WRAPPER_URL", "").strip():
            raise ValueError("Set APPLE_MUSIC_COOKIES and APPLE_MUSIC_WRAPPER_URL first.")
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
        return run(Path(__file__).with_name("scripts") / "apple_worker.py", url, output, args.limit, lyrics=args.lyrics)
    except ValueError as error:
        print(error, file=sys.stderr)
    except (OSError, KeyError):
        print("Could not start the worker or save the local output.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

