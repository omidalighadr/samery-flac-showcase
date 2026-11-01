# Samery

### Apple Music links → FLAC audio in Telegram

A private Telegram bot built by **Omid Alighadr**, focused on receiving Apple Music links and delivering FLAC audio files with track metadata and cover artwork.

**This repository is a product showcase. The source code is private.**

## The experience

1. Send an Apple Music track or album link to the bot.
2. Follow the request's progress in Telegram.
3. Receive the resulting audio with its title, artist, album, artwork and available quality information.

## A measured output sample

![Illustrated output card based on inspected file metadata](assets/sample-output.svg)

The card illustrates a real, previously saved output file. It is not a screenshot of Telegram.

| Property | Observed value |
| --- | --- |
| Track | Null Moon — Akira Yamaoka |
| Album | Silent Hill 2 (Original Soundtrack) |
| Audio codec | FLAC |
| Bit depth / sample rate | 16-bit / 44.1 kHz |
| Channels | Stereo |
| Duration | 170.307 seconds |
| Embedded artwork | Detected |
| Complete audio decode | Passed |

[Read the sample validation report](validation/sample-report.json), including its inspection timestamp and file checksum.

## What was tested

- **FFprobe inspection:** identified the audio codec, bit depth, sample rate, duration and embedded artwork.
- **FFmpeg full decode:** the complete audio stream decoded without a reported error under strict error handling.

The check was performed on an existing local output on **1 November 2026**. It was not a fresh download test. No reference-master or PCM-equivalence comparison was performed; FLAC metadata alone does not prove the quality of an upstream source.

## Scope and availability

This page demonstrates a private project and one measured output. It does not claim universal catalog availability, guaranteed uptime, or the same resolution for every recording. Availability and delivery depend on the account, region and Telegram transport.

No application source, credentials, cookies, databases, private logs or complete music files are included here.

Built with **Python · Telegram · FFmpeg · FFprobe**.
