# Samery · Apple Music to FLAC

A Python command-line tool that saves verified FLAC files from Apple Music song, album and playlist links to a local folder.

**Live downloads require** your own Apple Music account and private session, plus a compatible external service. The public snapshot has an offline verification demo. A fresh Python 3.12 environment on macOS successfully downloaded one track using an existing, separately configured local legacy service. The resulting 24-bit / 44.1 kHz FLAC passed a full decode. The external service setup and v2 live path were outside this check.

## Try it offline

With Python 3.12, FFmpeg and FFprobe installed:

```sh
python -m pip install 'mutagen>=1.47,<2'
python apple_music/demo.py
```

The demo generates a tone, encodes it to ALAC, converts it to FLAC and checks that the decoded PCM matches. It uses temporary files and requires no account or network. See the [automated PCM verification runs](https://github.com/omidalighadr/samery-flac-showcase/actions/workflows/offline-flac.yml).

## Set up live downloads

Read the [setup guide](docs/SETUP.md) for prerequisites, configuration and the download command. The external service and the private deployment's patched dependency are separate from this repository.

## Source

- [Command-line entry point](apple_music/download.py) validates links and saves local output.
- [Download worker](apple_music/scripts/apple_worker.py) connects the account and external service to the local audio pipeline.
- [Audio conversion](apple_music/scripts/apple_audio.py) checks codec, bit depth, sample rate, channel count and decoded PCM.
- [Source provenance](apple_music/source-manifest.json) lists checksums for the extracted worker modules.

Built around [GAMDL](https://github.com/glomatico/gamdl) and FFmpeg. Upstream components retain their own licenses. No additional reuse license has been selected for this repository. Use only accounts and media you are authorized to use.
