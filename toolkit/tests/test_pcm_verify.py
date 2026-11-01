"""Integration tests generate their own audio; no downloads or account required."""

from __future__ import annotations

import contextlib
import io
import json
import math
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import pcm_verify


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg and FFprobe required"
)
class PCMIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def wav(self, name="source.wav", *, bits=16, rate=44100, channels=2, changed=False):
        path = self.root / name
        frames = bytearray()
        for index in range(4096):
            for channel in range(channels):
                value = int(
                    math.sin(index * (0.031 + channel * 0.019))
                    * ((1 << (bits - 1)) - 1)
                    * 0.7
                )
                if changed and index == 100 and channel == 0:
                    value += 1
                frames.extend(value.to_bytes(bits // 8, "little", signed=True))
        with wave.open(str(path), "wb") as output:
            output.setnchannels(channels)
            output.setsampwidth(bits // 8)
            output.setframerate(rate)
            output.writeframes(bytes(frames))
        return path

    def convert(self, source, name, *options):
        output = self.root / name
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(source),
                *options,
                str(output),
            ],
            check=True,
            capture_output=True,
        )
        return output

    def test_alac_to_flac_preserves_16_and_24_bit_mono_and_stereo(self):
        for bits in (16, 24):
            for rate in (44100, 48000):
                for channels in (1, 2):
                    with self.subTest(bits=bits, rate=rate, channels=channels):
                        wav = self.wav(bits=bits, rate=rate, channels=channels)
                        alac = self.convert(wav, "source.m4a", "-c:a", "alac")
                        flac = self.convert(alac, "candidate.flac", "-c:a", "flac")
                        report = pcm_verify.compare(alac, flac)
                        self.assertTrue(report.equivalent)
                        self.assertEqual(report.source.bit_depth, bits)
                        self.assertEqual(report.source_sha256, report.candidate_sha256)

    def test_one_changed_sample_is_detected(self):
        report = pcm_verify.compare(self.wav(), self.wav("changed.wav", changed=True))
        self.assertFalse(report.equivalent)
        self.assertEqual(report.differences, ("decoded_pcm",))

    def test_matching_samples_at_different_rates_are_not_equivalent(self):
        report = pcm_verify.compare(self.wav(), self.wav("rate.wav", rate=48000))
        self.assertEqual(report.source_sha256, report.candidate_sha256)
        self.assertEqual(report.differences, ("sample_rate",))

    def test_channel_count_change_is_detected(self):
        report = pcm_verify.compare(self.wav(), self.wav("mono.wav", channels=1))
        self.assertIn("channels", report.differences)

    def test_metadata_does_not_change_pcm_equivalence(self):
        source = self.convert(self.wav(), "source.flac", "-c:a", "flac")
        tagged = self.convert(
            source,
            "tagged.flac",
            "-c:a",
            "copy",
            "-metadata",
            "title=Different metadata",
        )
        self.assertTrue(pcm_verify.compare(source, tagged).equivalent)

    def test_lossy_source_is_rejected(self):
        source = self.wav()
        lossy = self.convert(source, "lossy.m4a", "-c:a", "aac")
        with self.assertRaises(pcm_verify.VerificationError):
            pcm_verify.compare(lossy, source)

    def test_corrupt_input_is_rejected(self):
        invalid = self.root / "invalid.flac"
        invalid.write_bytes(b"not a valid audio file")
        with self.assertRaises(pcm_verify.VerificationError):
            pcm_verify.compare(self.wav(), invalid)

    def test_cli_json_and_exit_codes(self):
        source = self.wav()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(pcm_verify.main([str(source), str(source), "--json"]), 0)
        self.assertTrue(json.loads(output.getvalue())["equivalent"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                pcm_verify.main(
                    [str(source), str(self.wav("other.wav", changed=True)), "--json"]
                ),
                1,
            )
            self.assertEqual(
                pcm_verify.main(
                    [str(source), str(self.root / "missing.wav"), "--json"]
                ),
                2,
            )

    def test_input_changed_mid_verification_is_rejected(self):
        source = self.wav()

        def change_input(*args, **kwargs):
            source.write_bytes(source.read_bytes() + b"changed")
            return "0" * 64

        with patch.object(pcm_verify, "pcm_sha256", side_effect=change_input):
            with self.assertRaises(pcm_verify.VerificationError):
                pcm_verify.compare(source, source)


class ProcessErrorTests(unittest.TestCase):
    def test_missing_binary_is_clear(self):
        with self.assertRaises(pcm_verify.VerificationError):
            pcm_verify._run(["this-executable-does-not-exist"], 1)

    def test_timeout_is_clear(self):
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 1)
        ):
            with self.assertRaises(pcm_verify.VerificationError):
                pcm_verify._run(["ffmpeg"], 1)

    def test_decoder_error_does_not_expose_stderr(self):
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, "", "private filename"),
        ):
            with self.assertRaises(pcm_verify.VerificationError) as error:
                pcm_verify._run(["ffmpeg"], 1)
        self.assertNotIn("private filename", str(error.exception))


if __name__ == "__main__":
    unittest.main()
