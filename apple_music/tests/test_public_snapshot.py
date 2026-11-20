"""Check the public source boundary without loading local account settings."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PublicSnapshotTests(unittest.TestCase):
    def test_manifest_contains_only_matching_integration_modules(self):
        manifest = json.loads((ROOT / "apple_music/source-manifest.json").read_text())
        allowed = {"apple_audio.py", "apple_legacy.py", "apple_resume_ids.py", "apple_session.py",
                   "apple_worker.py", "music_metadata.py", "apple_stream.py", "apple_collection_catalog.py"}
        self.assertEqual({Path(row["path"]).name for row in manifest["files"]}, allowed)
        for row in manifest["files"]:
            path = ROOT / "apple_music" / row["path"]
            self.assertTrue(path.resolve().is_relative_to(ROOT / "apple_music/scripts"))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])

    def test_public_sources_do_not_contain_deployment_credentials(self):
        # Local ignored runtime files are outside this source-only check.
        for path in ROOT.rglob("*"):
            if not path.is_file() or any(p.startswith(".") for p in path.relative_to(ROOT).parts[:-1]):
                continue
            if path.suffix not in (".py", ".md", ".json", ".svg", ".yml"):
                continue
            text = path.read_text()
            self.assertNotRegex(text, r"/Users/[^/\s]+/Library/Application Support/")
            self.assertNotRegex(text, r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")
            self.assertNotRegex(text, r"\beyJ[A-Za-z0-9_-]{20,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b")
            self.assertNotIn("-----BEGIN " + "PRIVATE KEY-----", text)


if __name__ == "__main__":
    unittest.main()
