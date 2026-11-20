# Samery · Apple Music to FLAC

A standalone Python CLI for saving Apple Music tracks, albums and playlists as
verified FLAC files. This is the public download integration used by Samery;
the private Telegram deployment is maintained separately.

## What is included

- Track, album and playlist links, with up to 50 items per request.
- Original ALAC bit depth, sample rate and channel count preserved during FLAC
  conversion, with decoded PCM compared before accepting the result.
- Complete fragment downloads with bounded retries for transient failures.
- Output duration checked against catalog metadata when available, followed by
  a full decode with FFmpeg's error checks enabled.
- Artwork, title, artist, release date, Apple Music ID and available lyrics kept
  in the FLAC tags.
- Readable `Artist - Title.flac` filenames; whole-album downloads add disc/track
  prefixes such as `01-03 Artist - Title.flac`. Existing files are preserved.
- An account-bootstrap helper that retries temporary network failures and avoids
  forwarding account credentials to a redirect target.
- A catalog helper for paginated album/playlist lists, with bounded size and
  duplicate-ID removal. The CLI still uses the download worker for live audio.

These checks detect reported decode errors and many shortened outputs. They do
not prove source authenticity or rule out an earlier lossy conversion. Duration
comparison allows a difference of up to the larger of 2 seconds or 1%; missing
catalog duration cannot establish completeness against the original recording.

## Get the latest source

```sh
git clone https://github.com/omidalighadr/samery-flac-showcase.git
cd samery-flac-showcase
```

Or download the [current main-branch ZIP](https://github.com/omidalighadr/samery-flac-showcase/archive/refs/heads/main.zip).
The older `v0.1.0` release remains a historical snapshot.

## Offline demo

Requirements: Python 3.12, FFmpeg and FFprobe on PATH.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install 'mutagen>=1.47,<2'
python apple_music/demo.py
```

The demo generates an ALAC tone locally, converts it to FLAC and compares its
decoded PCM. It needs no account or network connection after installing the
requirements.

```text
Verified tone.flac: 16-bit, 44100 Hz. PCM matches.
```

## Live downloads

Follow the [setup guide](docs/SETUP.md) and use your own active Apple Music
subscription, private session cookie file and independently configured compatible
service. The external service is not bundled. The integration targets GAMDL
3.9.1 and retains both v2 and local-only legacy adapters.

```sh
python -m pip install -r apple_music/requirements.txt
# Configure your own local settings as explained in docs/SETUP.md.
python apple_music/download.py "$APPLE_MUSIC_LINK" --output downloads
python apple_music/download.py "$APPLE_MUSIC_LINK" --output downloads --lyrics
```

The CLI confirms a track only after saving its file. If a request ends partially,
completed files remain saved and the unfinished working directory is reported.
It does not persist a resumable CLI queue across restarts.

## Source update · 2026-11-20

The [source manifest](apple_music/source-manifest.json) records checksums for the
eight selected integration modules. This update includes the media transport,
catalog pagination, session bootstrap and metadata changes from the application.
The public CLI now uses the metadata filename helper and album numbering.
See [the changelog](CHANGELOG.md) for the update boundary.

Public source contains no account cookies, personal API credentials, Telegram
sessions, private deployment configuration, databases, logs or downloaded media.
The [sample environment file](.env.example) contains placeholders only. Keep
actual values local and out of Git.

## Validation

```sh
python -m unittest discover -s apple_music/tests -p 'test_*.py' -v
python apple_music/demo.py
python -m pip check
```

The 27 tests cover CLI saving, collision handling, filename numbering, catalog
pagination, session retries, redirect handling, transport retry budgets, duration
checks and real lossless conversion. Generated 16/24-bit audio fixtures verify
PCM, tags and original artwork at 44.1, 96 and 192 kHz. Other service requests are
simulated; no real cookies or API credentials are used by these checks.

[GitHub Actions](https://github.com/omidalighadr/samery-flac-showcase/actions/workflows/flac.yml)
installs the public dependencies and runs the same suite. Live downloads with
this snapshot, external-service installation, live v2 operation and Telegram
delivery were not tested as part of this update. A previous snapshot had a
macOS legacy-service live smoke test; that historical result is not a claim
about this snapshot.

## Private Telegram deployment

The running Samery bot also has channel publishing, album cards, large-file
Telegram delivery and a music ZIP workflow. Those application features are not
included in this standalone CLI. The illustration below uses synthetic data:

![Illustrative Samery output with synthetic artwork and metadata](docs/samery-output-example.svg)

Built using [GAMDL](https://github.com/glomatico/gamdl) and FFmpeg. Upstream
components retain their licenses. Use your own account and media you are
authorized to use.
