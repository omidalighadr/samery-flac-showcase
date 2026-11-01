# Samery · Apple Music integration source

The original download worker and supporting modules extracted from the private Samery application on **1 November 2026**. This directory now publishes the Apple Music integration source, rather than only the audio verification utilities.

## Source map

| Module | Responsibility |
| --- | --- |
| `scripts/apple_worker.py` | GAMDL integration, media iteration, progress events and per-track acknowledgement |
| `scripts/apple_session.py` | Account bootstrap and bounded network retries with redacted diagnostics |
| `scripts/apple_legacy.py` | Loopback protocol adapter for an externally operated Wrapper service |
| `scripts/apple_audio.py` | ALAC-to-FLAC conversion, format checks and decoded PCM comparison |
| `scripts/apple_resume_ids.py` | Validation of completed-track snapshots |
| `scripts/music_metadata.py` | Embedded lyrics, artwork thumbnails, captions and filenames |
| `services/ordered_albums.py` | Extracted pure helpers for disc/track ordering and filename prefixes |

The six script modules are unchanged source snapshots. Their checksums are in [`source-manifest.json`](source-manifest.json). Tests were selected from the original regression suite and isolated from the private bot's fixtures. The running application was not modified to create this snapshot.

## Dependencies and attribution

This project integrates [GAMDL](https://github.com/glomatico/gamdl); it does not claim to implement the underlying downloader independently. The protocol adapter references [WorldObservationLog/wrapper](https://github.com/WorldObservationLog/wrapper) and [glomatico/wrapper-v2](https://github.com/glomatico/wrapper-v2). Upstream code, binaries and their licenses remain with their respective projects and are not bundled here.

Required externally:

- Python 3.12, FFmpeg and FFprobe.
- The runtime dependencies in `requirements.txt` (GAMDL API target: 3.9.1).
- Your own active Apple Music subscription and private session cookie file.
- An independently configured and authenticated compatible Wrapper for lossless operation. The adapter is not the Wrapper daemon itself.

**Portability limit:** the private deployment also has a locally patched dependency wheel. That wheel, virtual environments, VM images and service state are not included. A clean-install end-to-end download has not been validated from this public snapshot. Installing `requirements.txt` alone is not a claim that the external service is ready.

No tokens, cookies, credentials, account exports, databases, private filesystem paths or downloaded recordings are distributed. `.env.example` contains names and empty values only; the worker uses explicit arguments and does not automatically read that template.

## Worker interface

From this directory, inspect the CLI without loading credentials:

```sh
python3 scripts/apple_worker.py --help
```

The worker is a subprocess component. The standalone [`bot.py`](bot.py) now supplies its Telegram front end; see the [setup guide](../docs/SETUP.md). It emits JSON-line events on stdout (`ready`, `stage`, `track`, `resume`, `track_error`, `done`, `error`). Third-party logs are suppressed. A `track` event points to a file in the caller-provided output directory.

**Acknowledgement matters:** after emitting a track, the worker waits for a line on stdin. Any line acknowledges the track and permits deletion of that output and its lyrics. The parent must only acknowledge after successful delivery or a verified durable copy. EOF returns without acknowledging the current file. Use an isolated scratch output directory, not your existing music library.

The `flac` selection requests ALAC only and does not fall back to AAC. Conversion keeps the source bit depth and sample rate, checks channels and compares decoded PCM hashes. This verifies equality to the supplied ALAC file; it does not prove the provenance of the upstream recording or guarantee a particular resolution for every release.

## What this snapshot excludes

The private application's handlers, token, authorization database, channel settings and deployment are not included. A new standalone Telegram front end and Docker configuration are included for this public project; they do not reproduce the complete personal assistant. The separate [`toolkit/`](../toolkit/) directory contains optional local audio utilities.

## Tests

From this directory, with FFmpeg/FFprobe available:

```sh
python3 -m pip install -r requirements-test.txt
python3 -m pytest tests -q
```

Tests generate synthetic audio and use mocked HTTP responses and loopback protocol fixtures. They do not authenticate to Apple, download commercial recordings, or establish that an external Wrapper is currently functioning. The public Actions workflow runs these isolated checks separately from the standalone audio toolkit tests.

Account availability, regional restrictions and upstream API changes can affect operation. Use your own account and only process and share media you are authorized to use. Apple, Telegram and the referenced upstream projects do not endorse this project.

Local validation on 1 November 2026: **17 passed, 1 skipped** on Python 3.12. The loopback integration test was skipped because the local execution environment prohibits socket listeners; it remains enabled in hosted CI. These results do not establish a live Apple Music download.
