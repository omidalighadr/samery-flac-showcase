"""Upload an existing local FLAC document; never download, convert or delete it."""
import argparse
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import sys

from pcm_verify import VerificationError, probe, pcm_sha256

LIMIT = 50 * 1024 * 1024


def fingerprint(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


class DeliveryError(Exception):
    pass


def send(path, token, chat_id):
    path = Path(path).expanduser().resolve()
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
        raise DeliveryError("Configure TELEGRAM_BOT_TOKEN privately.")
    if not re.fullmatch(r"-?[0-9]+", str(chat_id)):
        raise DeliveryError("Configure a numeric TELEGRAM_CHAT_ID.")
    before = path.stat()
    if not 0 < before.st_size < LIMIT:
        raise DeliveryError("File must be smaller than 50 MiB; original kept.")
    info = probe(path)
    if info.codec != "flac":
        raise DeliveryError("Only existing FLAC audio is accepted.")
    pcm_sha256(path)  # Full decode before upload; do not infer quality from a suffix.
    if fingerprint(path.stat()) != fingerprint(before):
        raise DeliveryError("File changed during validation; original kept.")
    boundary = "samery" + secrets.token_hex(16)
    prefix = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n"
        f"{chat_id}\r\n--{boundary}\r\n"
        'Content-Disposition: form-data; name="document"; filename="audio.flac"\r\n'
        "Content-Type: audio/flac\r\n\r\n"
    ).encode()
    suffix = f"\r\n--{boundary}--\r\n".encode()
    conn = http.client.HTTPSConnection("api.telegram.org", timeout=180)
    try:
        with path.open("rb") as source:
            if fingerprint(os.fstat(source.fileno())) != fingerprint(before):
                raise DeliveryError("File changed before upload; original kept.")
            conn.putrequest("POST", f"/bot{token}/sendDocument")
            conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
            conn.putheader("Content-Length", str(len(prefix) + before.st_size + len(suffix)))
            conn.endheaders()
            conn.send(prefix)
            remaining = before.st_size
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise DeliveryError("File changed during upload. Check Telegram before retrying.")
                conn.send(chunk)
                remaining -= len(chunk)
            conn.send(suffix)
        response = conn.getresponse()
        raw = response.read(1024 * 1024)
        data = json.loads(raw)
        if response.status != 200 or not data.get("ok"):
            raise DeliveryError("Telegram rejected the upload; original kept.")
        result = data["result"]
        if result.get("document", {}).get("file_size") != before.st_size:
            raise DeliveryError("Receipt could not be verified. Check Telegram before retrying.")
        return result["message_id"]
    except DeliveryError:
        raise
    except Exception:
        # Never print request URLs: they contain the bot token.
        raise DeliveryError("Delivery is uncertain. Check Telegram before retrying; original kept.") from None
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file")
    args = parser.parse_args()
    try:
        message_id = send(args.file, os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", ""))
        print(json.dumps({"sent": True, "message_id": message_id}))
        return 0
    except (DeliveryError, VerificationError, OSError):
        print("Upload not confirmed. Check configuration and Telegram before retrying. Original kept.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
