# Setup

[Project overview](../README.md)

## Requirements

- Python 3.12 and FFmpeg with FFprobe available on PATH.
- Your own active Apple Music subscription and a private Netscape-format session cookie file.
- An independently configured compatible external service. This snapshot targets GAMDL 3.9.1. It supports the v2 service interface and the existing local-only legacy adapter. The service itself and the private deployment's patched dependency wheel are separate.

Validated on macOS in a fresh Python 3.12 environment with dependencies installed from PyPI. One track downloaded through an existing legacy local service and passed a full FLAC decode. The offline demo verifies generated audio, and the CLI tests use a simulated worker. The service installation itself and the live v2 path were outside this check.

## Install

From the repository root:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r apple_music/requirements.txt
```

Set `APPLE_MUSIC_COOKIES` to the path of your private cookie file and `APPLE_MUSIC_WRAPPER_URL` to the URL of your compatible service in your local shell. Keep the cookie file outside the repository or under its ignored `private/` directory.

For an existing legacy local service, set `APPLE_MUSIC_WRAPPER_BACKEND=legacy-local`. The default is `v2`. If your v2 service uses custom connection settings, set `APPLE_MUSIC_DECRYPT_HOST` and `APPLE_MUSIC_DECRYPT_PORT` as appropriate.

## Run

```sh
python apple_music/download.py --help
python apple_music/download.py "$APPLE_MUSIC_LINK" --output downloads
```

Set `APPLE_MUSIC_LINK` to a song, album or playlist link. The CLI processes up to 50 items per request and saves each finished FLAC before acknowledging it to the worker. Existing files with matching names are preserved. If an operation fails, inspect the hidden `.samery-*` folder inside the selected output directory for unfinished files.

## Verify without an account

```sh
python apple_music/demo.py
python -m unittest discover -s apple_music/tests -p test_download_cli.py -v
```
