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


def save_track(event, work, destination):
    raw = event.get("path")
    if not isinstance(raw, str) or not raw:
        raise ValueError("Worker produced an invalid output path.")
    source = Path(raw).resolve(strict=True)
    if not source.is_relative_to(work) or not source.is_file() or source.suffix.lower() != ".flac":
        raise ValueError("Worker produced an invalid output path.")
    for index in range(1, 1001):
        name = source.name if index == 1 else f"{source.stem} ({index}){source.suffix}"
        target = destination / name
        try:
            os.link(source, target)
        except FileExistsError:
            continue
        return target
    raise ValueError("Too many files have the same name.")


def run(worker, url, destination, limit):
    destination = destination.resolve()
    work = Path(tempfile.mkdtemp(prefix=".samery-", dir=destination)).resolve()
    confirmed = 0
    done = None
    error = False
    cmd = [sys.executable, "-B", str(worker), "--url", url, "--output", str(work),
           "--limit", str(limit), "--codec", "flac"]
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
                    target = save_track(event, work, destination)
                    process.stdin.write("saved\n")
                    process.stdin.flush()
                    confirmed += 1
                    print(f"Saved: {target.name!r}", flush=True)
                elif kind == "done":
                    done = event
                elif kind in ("error", "track_error"):
                    error = True
            returncode = process.wait()
        except BaseException:
            if process.poll() is None:
                process.kill()
            raise
    if returncode or error or done is None or not confirmed or done.get("failed"):
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
    args = parser.parse_args(argv)
    try:
        url = catalog_url(args.url)
        if not 1 <= args.limit <= 50:
            raise ValueError("Limit must be between 1 and 50.")
        if not Path(os.environ.get("APPLE_MUSIC_COOKIES", "")).is_file() or not os.environ.get("APPLE_MUSIC_WRAPPER_URL", "").strip():
            raise ValueError("Set APPLE_MUSIC_COOKIES and APPLE_MUSIC_WRAPPER_URL first.")
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
        return run(Path(__file__).with_name("scripts") / "apple_worker.py", url, output, args.limit)
    except ValueError as error:
        print(error, file=sys.stderr)
    except (OSError, KeyError):
        print("Could not start the worker or save the local output.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
