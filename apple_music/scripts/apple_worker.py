"""Private JSON-line bridge to the separately pinned gamdl runtime (3.9.1)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import shutil
import sys


def emit(event: str, **values) -> None:
    os.write(1, (json.dumps(dict(event=event, **values)) + "\n").encode())


def codec_priority(codec: str) -> list[str]:
    return ["alac"] if codec == "flac" else list(dict.fromkeys([codec, "aac-web", "aac-he-web"]))


async def run(args) -> None:
    # Third-party diagnostics can contain playback URLs and account details.
    # Only our explicit, non-secret protocol events leave this process.
    sys.stdout = sys.stderr
    logging.disable(logging.CRITICAL)
    import structlog

    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(50))
    from gamdl.api import AppleMusicApi
    from apple_session import resilient_api

    AppleMusicApi = resilient_api(AppleMusicApi)
    from gamdl.api.wrapper import WrapperApi
    from gamdl.interface import (
        AppleMusicBaseInterface,
        AppleMusicInterface,
        AppleMusicSongInterface,
        AppleMusicMusicVideoInterface,
        AppleMusicUploadedVideoInterface,
    )
    from gamdl.interface.enums import SongCodec
    from gamdl.downloader import (
        AppleMusicBaseDownloader,
        AppleMusicDownloader,
        AppleMusicSongDownloader,
        AppleMusicMusicVideoDownloader,
        AppleMusicUploadedVideoDownloader,
    )

    api = None
    base = None
    wrapper = None
    try:
        args.stage = "authentication"
        api = await AppleMusicApi.create_from_netscape_cookies(cookies_path=args.cookies)
        import httpx

        api.client.timeout = httpx.Timeout(45, connect=30)
        if not api.active_subscription:
            emit("error", code="subscription")
            return
        if args.check:
            emit("ready")
            return
        if args.wrapper:
            args.stage = "wrapper"
            if args.wrapper_backend == "legacy-local":
                from apple_legacy import LegacyWrapper

                wrapper = await LegacyWrapper(api).start()
            else:
                wrapper = await WrapperApi.create(
                    base_url=args.wrapper,
                    decrypt_host=args.decrypt_host,
                    decrypt_port=args.decrypt_port,
                )
        args.stage = "media_setup"
        base = await AppleMusicBaseInterface.create(apple_music_api=api, wrapper_api=wrapper)
        codecs = codec_priority(args.codec)
        interface = AppleMusicInterface(
            song=AppleMusicSongInterface(base=base, codec_priority=[SongCodec(c) for c in codecs]),
            music_video=AppleMusicMusicVideoInterface(base=base),
            uploaded_video=AppleMusicUploadedVideoInterface(base=base),
            concurrency=1,
            disallowed_media_types=["music-videos", "uploaded-videos", "artists"],
        )
        output = Path(args.output).resolve()
        download_base = AppleMusicBaseDownloader(
            interface=interface,
            output_path=str(output),
            temp_path=str(output / "temp"),
            silent=True,
            truncate=100,
        )
        downloader = AppleMusicDownloader(
            song=AppleMusicSongDownloader(base=download_base),
            music_video=AppleMusicMusicVideoDownloader(base=download_base),
            uploaded_video=AppleMusicUploadedVideoDownloader(base=download_base),
            no_synced_lyrics=not args.lyrics,
        )
        from apple_resume_ids import load_completed, track_id
        completed_ids = load_completed(output, getattr(args, "completed", None))
        resumed = 0
        count = 0
        failed = 0
        args.stage = "download"
        async for item in downloader.get_download_item_from_url(args.url):
            if item.media.partial:
                continue
            media_id = track_id(item)
            if media_id in completed_ids:
                resumed += 1
                emit("resume", id=media_id)
                continue
            if count >= args.limit:
                emit("limit", count=args.limit)
                break
            count += 1
            try:
                emit(
                    "stage",
                    stage="download",
                    title=item.media.tags.title or "Apple Music",
                    index=count,
                )
                await downloader.download(item)
                path = Path(item.final_path).resolve()
                if not path.is_relative_to(output) or not path.is_file():
                    raise ValueError("Invalid output")
                tags = item.media.tags
                from music_metadata import embed_lyrics

                lyric_data = item.media.lyrics
                plain = getattr(lyric_data, "unsynced", None) or tags.lyrics or ""
                synced = getattr(lyric_data, "synced", None) or ""
                await asyncio.to_thread(embed_lyrics, path, plain, synced)
                quality = {}
                if args.codec == "flac":
                    from apple_audio import to_flac

                    emit("stage", stage="prepare", title=tags.title or "Apple Music", index=count)
                    original = path
                    path, quality = await asyncio.to_thread(
                        to_flac, path, args.ffmpeg, args.ffprobe
                    )
                    original.unlink()
                    if synced:
                        await asyncio.to_thread(embed_lyrics, path, plain, synced)
                lyrics = Path(item.synced_lyrics_path) if item.synced_lyrics_path else None
                emit(
                    "track",
                    path=str(path),
                    title=tags.title or "Apple Music",
                    artist=tags.artist or "",
                    album=tags.album or "",
                    id=str(tags.title_id or item.media.media_id),
                    date=str(tags.date or ""),
                    disc=tags.disc,
                    track=tags.track,
                    **quality,
                    format="FLAC"
                    if args.codec == "flac"
                    else getattr(
                        getattr(item.media.stream_info, "audio_track", None), "codec", None
                    )
                    or "Apple Music",
                    lyrics=str(lyrics.resolve())
                    if args.lyrics and lyrics and lyrics.is_file()
                    else "",
                )
                # Wait until upload completes: at most one finished track occupies disk.
                if not await asyncio.to_thread(sys.stdin.readline):
                    return
                path.unlink(missing_ok=True)
                if lyrics:
                    lyrics.unlink(missing_ok=True)
            except Exception as error:
                failed += 1
                emit("track_error", code=type(error).__name__)
        emit("done", count=count, failed=failed, resumed=resumed)
    finally:
        if args.wrapper_backend == "legacy-local" and wrapper is not None:
            await wrapper.aclose()
        for client in (
            getattr(api, "client", None),
            getattr(getattr(base, "itunes_api", None), "client", None),
            getattr(wrapper, "client", None),
        ):
            if client is not None:
                await client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cookies", required=True)
    parser.add_argument("--url", default="")
    parser.add_argument("--output", default=".")
    parser.add_argument("--codec", default="flac")
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    parser.add_argument("--ffprobe", default=shutil.which("ffprobe") or "ffprobe")
    parser.add_argument("--lyrics", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--completed", default="")
    parser.add_argument("--wrapper", default="")
    parser.add_argument("--wrapper-backend", choices=("v2", "legacy-local"), default="v2")
    parser.add_argument("--decrypt-host", default="127.0.0.1")
    parser.add_argument("--decrypt-port", type=int, default=10020)
    args = parser.parse_args()
    args.stage = "runtime"
    try:
        asyncio.run(run(args))
    except Exception as error:
        # Never include exception messages, HTTP headers, URLs or response bodies.
        code = getattr(error, "code", None)
        allowed = {
            "network",
            "apple_unavailable",
            "account_rejected",
            "apple_access_denied",
            "apple_response",
            "apple_page_changed",
        }
        if code not in allowed:
            code = {
                "wrapper": "wrapper_unavailable",
                "media_setup": "media_setup",
                "runtime": "runtime",
            }.get(args.stage, "account_or_network")
        emit("error", code=code, kind=type(error).__name__, stage=args.stage)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
