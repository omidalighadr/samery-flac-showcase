# Setup

[Project overview](../README.md)

## Requirements

- Python 3.12 and FFmpeg with FFprobe available on PATH.
- Your own active Apple Music subscription and a private Netscape-format session cookie file.
- An independently configured compatible external service. This snapshot targets GAMDL 3.9.1. It supports the v2 service interface and the existing local-only legacy adapter. The service itself and the private deployment's patched dependency wheel are separate.

This source update was checked in a fresh Python 3.12 environment with the public dependencies installed from PyPI. The tests use generated audio and simulated catalog/account responses. No account credentials were loaded and no live download was performed for this update. External service installation, live v2 operation and Telegram delivery remain outside these checks.

## Install

- macOS with Homebrew: `brew install python@3.12 ffmpeg`.
- Debian or Ubuntu: `sudo apt install ffmpeg`. Install Python 3.12 with venv support using your distribution's packages or your Python installation of choice.
- Confirm `python3.12 --version`, `ffmpeg -version`, and `ffprobe -version` all work.

From the repository root:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r apple_music/requirements.txt
```

Copy [the sample environment file](../.env.example) to `.env`, edit the placeholder values locally, and load them with `. ./.env` in that shell. The CLI reads the exported values.

Set `APPLE_MUSIC_COOKIES` to the path of your private cookie file and `APPLE_MUSIC_WRAPPER_URL` to the URL of your compatible service in your local shell. Keep the cookie file outside the repository or under its ignored `private/` directory.

For an existing legacy local service, set `APPLE_MUSIC_WRAPPER_BACKEND=legacy-local`. The default is `v2`. If your v2 service uses custom connection settings, set `APPLE_MUSIC_DECRYPT_HOST` and `APPLE_MUSIC_DECRYPT_PORT` as appropriate.

## Run

```sh
python apple_music/download.py --help
python apple_music/download.py "$APPLE_MUSIC_LINK" --output downloads
```

Set `APPLE_MUSIC_LINK` to a song, album or playlist link. The CLI processes up to 50 items per request and saves each finished FLAC before acknowledging it to the worker. Whole-album output uses disc/track prefixes and metadata-based artist/title filenames. Existing files with matching names are preserved. Add `--lyrics` to request available synchronized lyrics for embedding; separate lyric sidecars are not exported by this CLI. If an operation fails, inspect the hidden `.samery-*` folder inside the selected output directory for unfinished files.

### Example links

```sh
# Track
python apple_music/download.py 'https://music.apple.com/us/song/1109715066' --output downloads

# Album
python apple_music/download.py 'https://music.apple.com/us/album/in-rainbows/1109714933' --output downloads

# Playlist (save up to five tracks)
python apple_music/download.py 'https://music.apple.com/us/playlist/ennio-morricone-essentials/pl.dd4d7ac6f8fa4c098843ce267b3328cd' --limit 5 --output downloads
```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| The CLI asks for cookie and service settings | Open a new terminal, activate the virtual environment and load your edited `.env`. Verify the private session file exists and the service URL is set. |
| The compatible service is unavailable | Check that the service is running and reachable from the machine running the CLI. Confirm the configured interface matches the service. |
| A download ends with `Download incomplete` | Check the saved-file count and the reported `.samery-*` directory. Completed files already saved in the output folder are preserved. |
| A track fails duration or full-decode checks | Retry after checking your network and compatible service. The worker does not emit that output as a successfully verified track. |

## Verify without an account

```sh
python apple_music/demo.py
python -m unittest discover -s apple_music/tests -p 'test_*.py' -v
```


## Catalog helper

The worker can list catalog entries without downloading audio. This still uses
your own private Apple Music session for the catalog API, but does not require
the external playback service:

```sh
python apple_music/scripts/apple_worker.py --cookies "$APPLE_MUSIC_COOKIES" \
  --url "$APPLE_MUSIC_LINK" --catalog
```

Use an album or playlist link for this mode. The JSON-line response includes
bounded, deduplicated catalog song IDs and metadata. This is a low-level worker
interface; the normal download command remains `apple_music/download.py`.
