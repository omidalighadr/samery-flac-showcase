"""Transport and completeness regressions; no live service is contacted."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import apple_stream as stream


class StreamTests(unittest.TestCase):
    def test_transient_transport_retries_then_succeeds(self):
        queue = SimpleNamespace(put=lambda value: self.fail("unexpected failure"))
        with patch.object(stream, "_download_once", side_effect=[TimeoutError("synthetic"), None]) as download:
            with patch.object(stream.time, "sleep") as sleep:
                stream.download_stream_process("https://media.example/test", "unused", True, queue)
        self.assertEqual(download.call_count, 2)
        sleep.assert_called_once_with(2)

    def test_permanent_failure_is_not_retried(self):
        errors = []
        with patch.object(stream, "_download_once", side_effect=ValueError("synthetic")) as download:
            with patch.object(stream.time, "sleep") as sleep:
                stream.download_stream_process("https://media.example/test", "unused", True,
                                               SimpleNamespace(put=errors.append))
        self.assertEqual(download.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual(len(errors), 1)

    def test_network_retry_budget_is_bounded(self):
        errors = []
        with patch.object(stream, "_download_once", side_effect=TimeoutError("synthetic")) as download:
            with patch.object(stream.time, "sleep") as sleep:
                stream.download_stream_process("https://media.example/test", "unused", True,
                                               SimpleNamespace(put=errors.append))
        self.assertEqual(download.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(len(errors), 1)

    def test_public_failure_code_does_not_include_exception_text(self):
        self.assertEqual(stream.failure_code(TimeoutError("synthetic-sensitive-response")), "stream_network")
        self.assertEqual(stream.failure_code(ValueError("track_duration_mismatch")), "track_duration_mismatch")
        self.assertEqual(stream.failure_code(ValueError("synthetic-sensitive-response")), "track_download_failed")

    def test_missing_or_nonfinite_duration_is_rejected(self):
        for duration in (None, "0", "nan", "inf"):
            with self.subTest(duration=duration):
                probe = SimpleNamespace(stdout=json.dumps({"streams": [{"duration": duration}]}).encode())
                with patch.object(subprocess, "run", return_value=probe) as run:
                    with self.assertRaisesRegex(ValueError, "track_duration_missing"):
                        stream.verify_complete(Path("unused.flac"), {}, "ffmpeg", "ffprobe")
                self.assertEqual(run.call_count, 1)

    def test_shortened_duration_is_rejected_before_decode(self):
        probe = SimpleNamespace(stdout=b'{"streams":[{"duration":"1"}]}')
        with patch.object(subprocess, "run", return_value=probe) as run:
            with self.assertRaisesRegex(ValueError, "track_duration_mismatch"):
                stream.verify_complete(Path("unused.flac"), {"attributes": {"durationInMillis": 10000}},
                                       "ffmpeg", "ffprobe")
        self.assertEqual(run.call_count, 1)

    def test_decode_error_is_rejected(self):
        responses = [SimpleNamespace(stdout=b'{"streams":[{"duration":"1"}]}'),
                     SimpleNamespace(returncode=1)]
        with patch.object(subprocess, "run", side_effect=responses):
            with self.assertRaisesRegex(ValueError, "audio_decode_failed"):
                stream.verify_complete(Path("unused.flac"), {}, "ffmpeg", "ffprobe")

    def test_real_flac_matches_expected_duration(self):
        ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
        self.assertIsNotNone(ffmpeg, "FFmpeg is required for this regression")
        self.assertIsNotNone(ffprobe, "FFprobe is required for this regression")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "generated.flac"
            subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                            "sine=frequency=440:sample_rate=44100:duration=1", str(path)],
                           check=True, capture_output=True, timeout=30)
            stream.verify_complete(path, {"attributes": {"durationInMillis": 1000}}, ffmpeg, ffprobe)
            with self.assertRaisesRegex(ValueError, "track_duration_mismatch"):
                stream.verify_complete(path, {"attributes": {"durationInMillis": 10000}}, ffmpeg, ffprobe)


if __name__ == "__main__":
    unittest.main()
