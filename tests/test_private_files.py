"""Test private-file rules using synthetic filenames, without opening credentials."""
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def private_path(value):
    path = PurePosixPath(value)
    name = path.name.lower()
    if name in {'.env.example', '.env.sample'}:
        return False
    return (
        any(part.lower() in {'private', 'creds', 'data', 'downloads'} for part in path.parts)
        or name == '.env' or name.startswith('.env.') or 'cookie' in name
        or name.endswith(('.pem', '.key', '.db', '.sqlite', '.sqlite3', '.session'))
        or '.session-' in name or '.sqlite-' in name or '.sqlite3-' in name or '.db-' in name
        or name.startswith(('credentials', 'service-account')) and name.endswith('.json')
    )


class PrivateFiles(unittest.TestCase):
    def test_cookie_and_state_paths_are_ignored(self):
        paths = [
            'private/apple-cookies.txt', 'apple_music/private/apple-cookies.txt',
            'apple-cookies.txt', 'nested/account-Cookies.txt', '.env', '.env.production',
            'apple_music/.env', 'creds/account.json', 'account.session',
            'account.session-journal', 'state.sqlite3-wal', 'state.db-shm', 'secret.pem',
            'data/jobs/track.bin',
        ]
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(['git', 'init', '-q', directory], check=True)
            (Path(directory) / '.gitignore').write_bytes((ROOT / '.gitignore').read_bytes())
            for path in paths:
                with self.subTest(path=path):
                    result = subprocess.run(['git', '-C', directory, 'check-ignore', '-q', path])
                    self.assertEqual(result.returncode, 0)

    def test_templates_and_source_remain_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(['git', 'init', '-q', directory], check=True)
            (Path(directory) / '.gitignore').write_bytes((ROOT / '.gitignore').read_bytes())
            for path in ['.env.example', 'apple_music/.env.example', 'apple_music/bot.py', 'docs/SETUP.md']:
                with self.subTest(path=path):
                    result = subprocess.run(['git', '-C', directory, 'check-ignore', '-q', path])
                    self.assertEqual(result.returncode, 1)

    def test_policy_catches_cookie_but_allows_template(self):
        self.assertTrue(private_path('private/apple-cookies.txt'))
        self.assertTrue(private_path('account.session-journal'))
        self.assertFalse(private_path('apple_music/.env.example'))
        self.assertFalse(private_path('apple_music/scripts/music_metadata.py'))

    def test_no_current_tracked_private_paths(self):
        result = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-z'], capture_output=True, check=True)
        paths = result.stdout.decode().split('\0')
        self.assertEqual([path for path in paths if path and private_path(path)], [])


if __name__ == '__main__':
    unittest.main()
