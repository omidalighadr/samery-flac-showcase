"""Convert a generated ALAC tone to verified FLAC offline."""
from pathlib import Path
import shutil
import subprocess
import tempfile

from scripts.apple_audio import to_flac


def main():
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise SystemExit("Install FFmpeg and FFprobe to run the demo.")
    with tempfile.TemporaryDirectory(prefix="samery-flac-demo-") as directory:
        source = Path(directory) / "tone.m4a"
        subprocess.run(
            [ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi", "-i",
             "sine=frequency=440:sample_rate=44100:duration=1", "-c:a", "alac", str(source)],
            check=True, timeout=30,
        )
        result, quality = to_flac(source, ffmpeg, ffprobe)
        print(f"Verified {result.name}: {quality['bit_depth']}-bit, {quality['sample_rate']} Hz. PCM matches.")


if __name__ == "__main__":
    main()
