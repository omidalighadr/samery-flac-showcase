import io
import random
import shutil
import subprocess
import wave
import pytest
from scripts.apple_audio import to_flac, pcm_hash
from scripts.apple_worker import codec_priority


def test_flac_never_falls_back_to_aac():
    assert codec_priority("flac") == ["alac"]

def tools():
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg required for real audio conversion regression")
    return ffmpeg, ffprobe

def make_alac(tmp_path, bits, rate):
    ffmpeg, ffprobe = tools()
    wav = tmp_path / "source.wav"
    with wave.open(str(wav), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(bits // 8)
        audio.setframerate(rate)
        audio.writeframes(random.Random(17).randbytes(rate // 10 * 2 * bits // 8))
    path = tmp_path / "source.m4a"
    subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-i", str(wav), "-c:a", "alac", str(path)],
        capture_output=True,
        check=True,
        timeout=30,
    )
    return path, ffmpeg, ffprobe

@pytest.mark.parametrize("bits,rate", [(16, 44100), (24, 96000), (24, 192000)])
def test_real_lossless_conversion_preserves_samples_tags_and_cover(tmp_path, bits, rate):
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen.flac import FLAC
    from PIL import Image

    path, ffmpeg, ffprobe = make_alac(tmp_path, bits, rate)
    picture = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(picture, format="PNG")
    source = MP4(path)
    source["©nam"] = ["Synthetic lossless test"]
    source["©lyr"] = ["Synthetic lyric for a test."]
    source["©day"] = ["2020-07-04T12:00:00Z"]
    source["cnID"] = [123456789]
    source["covr"] = [MP4Cover(picture.getvalue(), imageformat=MP4Cover.FORMAT_PNG)]
    source.save()
    result, quality = to_flac(path, ffmpeg, ffprobe)
    assert quality == dict(bit_depth=bits, sample_rate=rate)
    assert pcm_hash(path, ffmpeg) == pcm_hash(result, ffmpeg)
    flac = FLAC(result)
    assert flac.info.bits_per_sample == bits
    assert flac.info.sample_rate == rate
    assert flac["title"] == ["Synthetic lossless test"]
    assert flac["lyrics"] == ["Synthetic lyric for a test."]
    assert flac["apple_music_id"] == ["123456789"]
    assert flac.pictures[0].data == picture.getvalue()
    from scripts.music_metadata import thumbnail

    thumb = thumbnail(result)
    assert thumb.name == "cover.jpg"
    assert len(thumb.getvalue()) < 200_000
    preview = Image.open(thumb)
    assert preview.format == "JPEG" and max(preview.size) <= 320
    assert flac.pictures[0].data == picture.getvalue()

def test_aac_input_is_rejected_before_conversion(tmp_path):
    path, ffmpeg, ffprobe = make_alac(tmp_path, 16, 44100)
    aac = tmp_path / "lossy.m4a"
    subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-i", str(path), "-c:a", "aac", str(aac)],
        capture_output=True,
        check=True,
        timeout=30,
    )
    with pytest.raises(ValueError, match="Lossy input rejected"):
        to_flac(aac, ffmpeg, ffprobe)
    assert not aac.with_suffix(".flac").exists()
