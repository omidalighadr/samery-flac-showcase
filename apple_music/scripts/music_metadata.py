"""Consistent channel captions and embedded lyrics, without altering audio."""

from __future__ import annotations

import datetime
import html
from pathlib import Path
import re


def first(tags, *keys):
    for key in keys:
        try:
            value = tags.get(key)
        except (KeyError, ValueError, TypeError):
            continue
        if value:
            return value[0] if isinstance(value, list) else value
    return None


def number(value):
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    try:
        result = int(str(value).split("/")[0])
        return result if result > 0 else None
    except (ValueError, TypeError):
        return None


def release_date(value):
    text = str(value or "").strip()
    if re.fullmatch(r"\d{4}", text):
        return text
    match = re.match(r"^(\d{4})[-/.]?(\d{2})[-/.]?(\d{2})(?:$|[T\s])", text)
    if match:
        try:
            date = datetime.date(*(int(n) for n in match.groups()))
            return date.strftime("%Y/%m/%d")
        except ValueError:
            pass
    return ""


def metadata(path=None, fallback=None):
    result = dict(fallback or {})
    if path is None:
        return result
    from mutagen import File

    audio = File(path)
    if audio is None:
        return result
    tags = audio.tags or {}
    for name, keys in {
        "title": ("title", "TIT2", "\xa9nam"),
        "artist": ("artist", "TPE1", "\xa9ART"),
        "album": ("album", "TALB", "\xa9alb"),
        "date": ("date", "TDRC", "\xa9day"),
        "id": ("apple_music_id", "itunes_track_id", "cnID"),
    }.items():
        value = first(tags, *keys)
        if value is not None:
            result[name] = str(value)
    for name, keys in {
        "disc": ("discnumber", "TPOS", "disk"),
        "track": ("tracknumber", "TRCK", "trkn"),
    }.items():
        value = number(first(tags, *keys))
        if value:
            result[name] = value
    fmt = type(audio).__name__.upper()
    if fmt == "MP4":
        fmt = "ALAC" if getattr(audio.info, "codec", "") == "alac" else "AAC"
    elif fmt == "WAVE":
        fmt = "WAV"
    result["format"] = fmt
    result["sample_rate"] = getattr(audio.info, "sample_rate", None) or result.get("sample_rate")
    result["duration"] = getattr(audio.info, "length", None)
    if fmt in ("FLAC", "ALAC", "WAV", "AIFF"):
        result["bit_depth"] = getattr(audio.info, "bits_per_sample", None) or result.get(
            "bit_depth"
        )
    else:
        result.pop("bit_depth", None)
    embedded = first(tags, "lyrics", "\xa9lyr")
    if not embedded and hasattr(tags, "getall"):
        embedded = tags.getall("USLT")
    result["lyrics_embedded"] = bool(embedded)
    return result


def caption(data, signature="", *, html_mode=False):
    def text(value, limit=256):
        value = str(value or "").strip()[:limit]
        return html.escape(value) if html_mode else value

    lines = ["🎵 " + text(data.get("title") or "Unknown title")]
    date = release_date(data.get("date"))
    if date:
        lines.append("📅 " + date)
    track, disc = number(data.get("track")), number(data.get("disc"))
    if track:
        lines.append("💿 " + (f"Disc {disc} - " if disc else "") + f"Track {track}")
    identifier = str(data.get("id") or "").strip()
    if identifier and not identifier.lower().startswith(("http://", "https://")):
        lines.append("🆔 " + text(identifier, 80))
    fmt = text(data.get("format") or "AUDIO", 20)
    bits, rate = number(data.get("bit_depth")), number(data.get("sample_rate"))
    quality = (
        f"{fmt} | {bits}Bit - {rate / 1000:g}kHz"
        if bits and rate
        else (f"{fmt} | {rate / 1000:g}kHz" if rate else fmt)
    )
    lines.append("💎 " + quality)
    if signature.strip():
        lines.append(text(signature, 128))
    return "\n\n".join(lines)


def thumbnail(path):
    """Fresh JPEG thumbnail for Telegram, separate from full embedded artwork."""
    import io

    from mutagen import File, MutagenError
    from PIL import Image, ImageOps

    try:
        audio = File(path)
        pictures = getattr(audio, "pictures", [])
        covers = (audio.tags or {}).get("covr", []) if type(audio).__name__ == "MP4" else []
        if pictures:
            data = next((p.data for p in pictures if p.type == 3), pictures[0].data)
        elif covers:
            data = bytes(covers[0])
        else:
            return None
        with Image.open(io.BytesIO(data)) as source:
            picture = ImageOps.exif_transpose(source).convert("RGB")
            picture.thumbnail((320, 320))
            out = io.BytesIO()
            picture.save(out, "JPEG", quality=85)
        out.seek(0)
        out.name = "cover.jpg"
        return out
    except (OSError, ValueError, TypeError, AttributeError, MutagenError):
        return None


def filename(path, data=None):
    """Public filename from tags; internal cache hashes stay private."""
    path = Path(path)
    try:
        info = metadata(path, data)
    except Exception:
        info = dict(data or {})
    fallback = re.sub(r"^(?:[a-f0-9]{16}-)+", "", path.stem)
    fallback = re.sub(r"^\d{1,3}[ ._-]+", "", fallback)
    title = str(info.get("title") or fallback).strip()
    artist = str(info.get("artist") or "").strip()
    name = f"{artist} - {title}" if artist else title
    name = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .") or "Music"
    from services.ordered_albums import prefix
    name = prefix(info) + name
    return name[:180].rstrip() + path.suffix.lower()


def embed_lyrics(path: Path, plain="", synced=""):
    """Tag only; never transcode, resample or invent unavailable lyrics."""
    plain, synced = (plain or "").strip(), (synced or "").strip()
    if not (plain or synced):
        return False
    from mutagen import File

    audio = File(path)
    if audio is None:
        return False
    if audio.tags is None:
        audio.add_tags()
    fmt = type(audio).__name__.upper()
    if fmt == "MP4":
        audio["\xa9lyr"] = [plain or synced]
    elif fmt == "MP3":
        from mutagen.id3 import USLT

        audio.tags.delall("USLT")
        audio.tags.add(USLT(encoding=3, lang="und", desc="", text=plain or synced))
    elif fmt in ("FLAC", "OGGVORBIS", "OGGOPUS"):
        audio["lyrics"] = plain or synced
        if synced:
            audio["syncedlyrics"] = synced
    else:
        return False
    audio.save()
    return True
