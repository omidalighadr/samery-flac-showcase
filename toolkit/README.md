# Samery audio toolkit

Public supporting utilities from the Samery project. This is **not** the Apple Music downloader or the complete running bot. There is no service login, stream extraction, decryption or account session handling here.

## Requirements

- Python 3.11 or newer; standard library only, no pip dependencies.
- FFmpeg and FFprobe on PATH.
- Your own Telegram bot token and numeric recipient ID, only for sending.

## Verify local audio

From the repository root:

```sh
python3 toolkit/pcm_verify.py source.m4a output.flac --json
```

Accepts local lossless integer ALAC, FLAC and PCM with 16, 24 or 32 bits. Compares decoded PCM hashes, sample rate, channels, bit depth and channel layout. Exit codes: 0 equivalent, 1 different, 2 invalid or failed verification. It cannot establish whether an upstream recording was originally lossless.

## Send an existing FLAC to Telegram

Create your bot through BotFather, start a chat with it, and configure your own private environment. Copy `.env.example` to `.env`, fill in the values, then run:

```sh
set -a
. ./.env
set +a
python3 toolkit/send_flac.py /absolute/path/to/audio.flac
```

The command probes and decodes the file before a single `sendDocument` request to the official Telegram endpoint. Uploading does not re-encode the audio. It streams file bytes in bounded chunks, checks the returned file size and prints a message ID on success. The transmitted filename is deliberately `audio.flac`; this minimal example does not reproduce the private bot's cover, caption or queue interface.

Files must be smaller than 50 MiB. Larger files stay local without an upload attempt. No file is ever deleted. There is no automatic retry: after an uncertain network response, check the chat before trying again. Upload transport tests use mocks and do not establish live Telegram connectivity. Use only files you are entitled to share.

## Docker

Place a readable `sample.flac` in `downloads/`, configure `.env`, then:

```sh
docker compose run --rm send
```

This is a one-shot command, not an always-on bot. The media mount is read-only. Docker configuration is supplied as an example; it has not been executed in the local validation session.

## Tests

```sh
cd toolkit
python3 -m unittest discover -s tests -v
```

Audio tests generate synthetic signals locally, including 16/24-bit mono/stereo ALAC-to-FLAC comparisons, altered samples, rate changes, corrupt inputs and lossy rejection. Delivery tests exercise size limits, success, rejection and uncertain responses without network access or real credentials.

The hosted CI configuration runs these tests on Python 3.11–3.13. A configuration file is not evidence of a passing hosted run; inspect Actions for its actual result.
