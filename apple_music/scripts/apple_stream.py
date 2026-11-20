"""Require every media fragment; incomplete streams must fail before muxing."""
from pathlib import Path
import traceback
import time


def _download_once(stream_url, download_path, silent):
    from yt_dlp import YoutubeDL
    from yt_dlp.downloader.hls import HlsFD
    from yt_dlp.downloader.http import HttpFD

    Path(download_path).parent.mkdir(parents=True, exist_ok=True)
    options = {
        "quiet": True,
        "no_warnings": True,
        "overwrites": True,
        "noprogress": silent,
        "allow_unplayable_formats": True,
        "concurrent_fragment_downloads": 2,
        "skip_unavailable_fragments": False,
        "fragment_retries": 8,
        "retries": 5,
        "socket_timeout": 30,
    }
    with YoutubeDL(options) as ydl:
        hls = stream_url.split("?")[0].endswith(".m3u8")
        downloader = HlsFD(ydl, ydl.params) if hls else HttpFD(ydl, ydl.params)
        info = {"url": stream_url}
        if hls:
            info.update(ext="mp4", protocol="m3u8")
        success, _ = downloader.download(download_path, info)
        if not success:
            raise RuntimeError("Media transport did not complete")
        path = Path(download_path)
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError("Empty media transport output")


def download_stream_process(stream_url, download_path, silent, result_queue):
    for attempt in range(3):
        try:
            _download_once(stream_url, download_path, silent)
            return
        except Exception as error:
            text=(type(error).__name__+" "+str(error)).lower()
            transient=any(marker in text for marker in ("ssl", "unexpected_eof", "timed out", "timeout", "connection reset", "connection aborted", "remote end closed", "http error 429", "http error 500", "http error 502", "http error 503", "http error 504", "media transport did not complete"))
            if transient and attempt < 2:
                time.sleep(2 ** (attempt+1))
                continue
            result_queue.put(("error", repr(error), traceback.format_exc()))
            return


def failure_code(error):
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    if status in (401, 403):
        return "account_rejected"
    if status == 429 or isinstance(status, int) and 500 <= status < 600:
        return "stream_network"
    text=(type(error).__name__+" "+str(error)).lower()
    if str(error) in {"track_duration_missing", "track_duration_mismatch", "audio_decode_failed"}:
        return str(error)
    if any(k in text for k in ("ssl", "unexpected_eof", "timeout", "timed out", "connection reset", "connection aborted", "remote end closed")):
        return "stream_network"
    if "local wrapper" in text or "decrypt failed" in text:
        return "wrapper_unavailable"
    if type(error).__name__ == "CalledProcessError":
        return "audio_preparation"
    return "track_download_failed"


def verify_complete(path, metadata, ffmpeg, ffprobe):
    """Reject shortened or undecodable output before publishing a track event."""
    import json, math, subprocess
    result = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'a:0', '-show_streams', '-of', 'json', str(path)], capture_output=True, check=True, timeout=30)
    stream = json.loads(result.stdout)['streams'][0]
    duration = float(stream.get('duration') or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('track_duration_missing')
    expected = ((metadata or {}).get('attributes') or {}).get('durationInMillis')
    if expected is not None:
        expected = float(expected) / 1000
        if not math.isfinite(expected) or expected <= 0 or abs(duration - expected) > max(2, expected * .01):
            raise ValueError('track_duration_mismatch')
    result = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-xerror', '-err_detect', 'explode', '-i', str(path), '-map', '0:a:0', '-f', 'null', '-'], capture_output=True, timeout=180)
    if result.returncode:
        raise ValueError('audio_decode_failed')
