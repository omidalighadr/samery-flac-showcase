# Samery · Apple Music Telegram Bot

**Apple Music links → FLAC files, artwork and track metadata in Telegram.**

A focused Python project by **Omid Alighadr**. This repository brings the download integration, a standalone Telegram front end, Docker configuration and tests together in one place.

[Get started](docs/SETUP.md) · [Browse the bot](apple_music/bot.py) · [Download integration](apple_music/README.md) · [Sample validation](validation/sample-report.json)

## What it does

- Accepts Apple Music track, album and playlist links from explicitly allowed users.
- Requests the best available ALAC source and converts it to FLAC without changing the sample rate or bit depth; no AAC fallback for FLAC.
- Sends a document with embedded artwork, a thumbnail and a readable track caption.
- Processes one request at a time, with a bounded in-memory queue, status and cancellation.
- Acknowledges working-file deletion only after a matching Telegram receipt or a verified retained copy.
- Keeps files at or above 50 MiB on the bot host. Unconfirmed deliveries stay on disk and are not blindly retried.

## Start here

Read the [setup guide](docs/SETUP.md) before running. You need your own Telegram bot token, allowlisted user IDs, active Apple Music account, private cookie file and independently configured compatible Wrapper service.

```sh
cp .env.example .env
# Fill in your own private settings and place your cookie file as described in the guide.
docker compose up --build -d
```

The repository does **not** include a ready-to-use account, Wrapper daemon, service image or credentials. Public source does not make those dependencies optional.

## Output example

![Illustrated sample output, based on inspected metadata](assets/sample-output.svg)

The illustration represents a previously saved **Null Moon — Akira Yamaoka** file: FLAC, 16-bit / 44.1 kHz, stereo, 170.307 seconds, with embedded artwork. The existing file passed a complete strict decode on **1 November 2026**. It is an illustration, not a Telegram screenshot or a new end-to-end download test. [Validation report](validation/sample-report.json).

## Project map

| Location | Purpose |
| --- | --- |
| [`apple_music/bot.py`](apple_music/bot.py) | Standalone Telegram app and safe delivery coordination |
| [`apple_music/scripts/`](apple_music/scripts/) | Original Apple Music worker, local adapter, FLAC conversion and metadata |
| [`docs/SETUP.md`](docs/SETUP.md) | Python and Docker setup, configuration and limitations |
| [`apple_music/tests/`](apple_music/tests/) | Integration component and bot coordination tests |
| [`toolkit/`](toolkit/) | Optional local audio comparison and standalone file-sending utilities |
| [`validation/`](validation/) | Measured output evidence |

## Validation and scope

The original integration modules were extracted from the private application; the standalone Telegram front end was added for this public project. This is not the source of the complete personal Samery assistant.

Audio tests use generated signals; HTTP, worker and Telegram interactions are mocked or use loopback fixtures. They cover PCM equality, artwork, format checks, rejected inputs, uncertain delivery, acknowledgement order and retention. See [Actions](https://github.com/omidalighadr/samery-flac-showcase/actions) for current hosted results. A successful test run or image build does not establish live account or Wrapper availability.

The private deployment uses a patched dependency wheel which is not distributed. Compatibility of a clean public dependency installation must be assessed separately from the existing private bot. Queue state is not persistent across restart; this reference app does not implement durable upload recovery or automatic replay.

No tokens, cookies, account sessions, private databases, personal configuration or complete recordings are included. Upstream components are credited in the [integration guide](apple_music/README.md). Use your own account and only process and share media you are authorized to use.

No open-source license has been selected; public visibility does not grant an additional reuse license.
