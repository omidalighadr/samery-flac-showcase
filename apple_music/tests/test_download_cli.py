import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import download

URL = "https://music.apple.com/us/album/example/42?i=45"
WORKER = """import argparse, json, sys
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--output')
args, _ = p.parse_known_args()
path = Path(args.output) / 'Track.flac'
path.write_bytes(b'fixture')
print(json.dumps(dict(event='track', path=str(path))), flush=True)
if sys.stdin.readline().strip() == 'saved':
    path.unlink()
    print(json.dumps(dict(event='done', failed=0)), flush=True)
"""


class DownloadTests(unittest.TestCase):
    def test_catalog_links_are_normalized(self):
        self.assertEqual(download.catalog_url(URL + "&tracking=1"), URL)
        with self.assertRaises(ValueError):
            download.catalog_url("https://music.apple.com.example.org/us/song/45")

    def test_saved_track_survives_ack_and_existing_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.py"
            worker.write_text(WORKER)
            (root / "Track.flac").write_bytes(b"previous")
            with patch.dict(os.environ, APPLE_MUSIC_COOKIES="test", APPLE_MUSIC_WRAPPER_URL="test"):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(download.run(worker, URL, root, 2), 0)
            self.assertEqual((root / "Track.flac").read_bytes(), b"previous")
            self.assertEqual((root / "Track (2).flac").read_bytes(), b"fixture")
            self.assertFalse(list(root.glob(".samery-*")))

    def test_album_filenames_use_tags_and_disc_track_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            work.mkdir()
            source = work / "0123456789abcdef-original.flac"
            source.write_bytes(b"fixture")
            event = dict(path=str(source), title="Generated / Track", artist="Generated: Artist",
                         disc=2, track=3)
            saved = download.save_track(event, work, root, ordered=True)
            self.assertEqual(saved.name, "02-03 Generated Artist - Generated Track.flac")
            self.assertEqual(saved.read_bytes(), b"fixture")

    def test_partial_download_reports_known_error_once_without_exposing_worker_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            worker = root / "worker.py"
            worker.write_text(WORKER + """
for code in ('wrapper_unavailable', 'wrapper_unavailable', 'sensitive-unknown-code', {}):
    print(json.dumps(dict(event='track_error', code=code, detail='sensitive-detail')))
""")
            stderr = io.StringIO()
            with patch.dict(os.environ, APPLE_MUSIC_COOKIES="test", APPLE_MUSIC_WRAPPER_URL="test"):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                    self.assertEqual(download.run(worker, URL, root, 2), 1)
            self.assertEqual((root / "Track.flac").read_bytes(), b"fixture")
            self.assertEqual(stderr.getvalue().count("wrapper_unavailable:"), 1)
            self.assertIn("Saved 1 file(s)", stderr.getvalue())
            self.assertNotIn("sensitive", stderr.getvalue())

    def test_track_outside_working_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / "work"
            work.mkdir()
            outside = root / "outside.flac"
            outside.write_bytes(b"fixture")
            with self.assertRaises(ValueError):
                download.save_track({"path": str(outside)}, work, root)


if __name__ == "__main__":
    unittest.main()

