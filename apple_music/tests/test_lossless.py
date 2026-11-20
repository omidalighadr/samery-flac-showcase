"""Real conversion fixtures are generated locally, with no downloaded music."""
import io
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

from mutagen.flac import FLAC
from mutagen.mp4 import MP4, MP4Cover
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.apple_audio import to_flac, pcm_hash
from scripts.apple_worker import codec_priority
from scripts.music_metadata import filename, thumbnail


class LosslessTests(unittest.TestCase):
    def test_flac_never_falls_back_to_aac(self):
        self.assertEqual(codec_priority("flac"), ["alac"])

    def test_samples_tags_and_original_artwork_are_preserved(self):
        ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
        self.assertIsNotNone(ffmpeg)
        self.assertIsNotNone(ffprobe)
        for bits, rate in ((16, 44100), (24, 96000), (24, 192000)):
            with self.subTest(bits=bits, rate=rate), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                wav = root / "source.wav"
                with wave.open(str(wav), "wb") as audio:
                    audio.setnchannels(2)
                    audio.setsampwidth(bits // 8)
                    audio.setframerate(rate)
                    audio.writeframes(random.Random(17).randbytes(rate // 10 * 2 * bits // 8))
                source = root / "source.m4a"
                subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-i", str(wav),
                                "-c:a", "alac", str(source)], check=True, capture_output=True, timeout=30)
                picture = io.BytesIO()
                Image.new("RGB", (8, 8), "red").save(picture, format="PNG")
                tags = MP4(source)
                tags["\xa9nam"] = ["Generated track"]
                tags["\xa9ART"] = ["Generated artist"]
                tags["\xa9lyr"] = ["Generated lyric"]
                tags["cnID"] = [123456789]
                tags["covr"] = [MP4Cover(picture.getvalue(), imageformat=MP4Cover.FORMAT_PNG)]
                tags.save()
                result, quality = to_flac(source, ffmpeg, ffprobe)
                self.assertEqual(quality, dict(bit_depth=bits, sample_rate=rate))
                self.assertEqual(pcm_hash(source, ffmpeg), pcm_hash(result, ffmpeg))
                flac = FLAC(result)
                self.assertEqual(flac["lyrics"], ["Generated lyric"])
                self.assertEqual(flac["apple_music_id"], ["123456789"])
                self.assertEqual(flac.pictures[0].data, picture.getvalue())
                self.assertEqual(filename(result), "Generated artist - Generated track.flac")
                preview = thumbnail(result)
                self.assertEqual(Image.open(preview).format, "JPEG")
                self.assertEqual(FLAC(result).pictures[0].data, picture.getvalue())

    def test_lossy_input_is_rejected(self):
        ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
        self.assertIsNotNone(ffmpeg)
        self.assertIsNotNone(ffprobe)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "lossy.m4a"
            subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                            "sine=frequency=440:duration=0.1", "-c:a", "aac", str(source)],
                           check=True, capture_output=True, timeout=30)
            with self.assertRaisesRegex(ValueError, "Lossy input rejected"):
                to_flac(source, ffmpeg, ffprobe)
            self.assertFalse(source.with_suffix(".flac").exists())


if __name__ == "__main__":
    unittest.main()
