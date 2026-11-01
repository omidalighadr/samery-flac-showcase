"""Standalone Telegram front end for the extracted Samery Apple Music worker."""
from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from telegram import ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from scripts.music_metadata import caption, filename, metadata, thumbnail

ROOT = Path(__file__).resolve().parent
UPLOAD_LIMIT = 50 * 1024 * 1024


def apple_url(text):
    """Accept exactly one catalog URL; never forward arbitrary hosts to the worker."""
    links = re.findall(r"https?://[^\s<>]+", text, re.I)
    if len(links) != 1:
        return ""
    try:
        parts = urlsplit(links[0].rstrip(".,،؛)]}\"'"))
        if parts.netloc.lower() != "music.apple.com":
            return ""
        if not re.fullmatch(r"/[a-zA-Z]{2}/(?:album|song|playlist)/(?:[^/?#]+/)?(?:\d+|pl\.[\w-]+)", parts.path):
            return ""
        identifier = parse_qs(parts.query).get("i", [""])[0]
        if identifier and not identifier.isdigit():
            return ""
        return urlunsplit(("https", "music.apple.com", parts.path, urlencode({"i": identifier}) if identifier else "", ""))
    except ValueError:
        return ""


@dataclass(frozen=True)
class Settings:
    token: str
    allowed: frozenset[int]
    cookies: Path
    data: Path
    wrapper: str
    backend: str = "v2"
    decrypt_host: str = "127.0.0.1"
    decrypt_port: int = 10020

    @classmethod
    def from_env(cls):
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        allowed = frozenset(int(x.strip()) for x in os.environ.get("ALLOWED_USER_IDS", "").split(",") if x.strip())
        cookie_value = os.environ.get("APPLE_MUSIC_COOKIES", "").strip()
        if not re.fullmatch(r"\d+:[A-Za-z0-9_-]+", token) or not allowed or min(allowed) <= 0 or not cookie_value:
            raise ValueError("Missing private configuration")
        cookies = Path(cookie_value).expanduser().resolve()
        if not cookies.is_file():
            raise ValueError("Cookies file is missing")
        wrapper = os.environ.get("APPLE_MUSIC_WRAPPER_URL", "").strip()
        backend = os.environ.get("APPLE_MUSIC_WRAPPER_BACKEND", "v2")
        if not wrapper or backend not in ("v2", "legacy-local"):
            raise ValueError("External music service is not configured")
        data = Path(os.environ.get("DATA_DIR", "./data")).expanduser().resolve()
        data.mkdir(parents=True, exist_ok=True, mode=0o700)
        return cls(token, allowed, cookies, data, wrapper, backend,
                   os.environ.get("APPLE_MUSIC_DECRYPT_HOST", "127.0.0.1"),
                   int(os.environ.get("APPLE_MUSIC_DECRYPT_PORT", "10020")))


def managed_file(value, directory):
    raw = Path(value)
    result = raw.resolve()
    if raw.is_symlink() or not result.is_relative_to(directory.resolve()) or not result.is_file():
        raise ValueError("Worker output is outside its job")
    return result


async def deliver(bot, chat_id, path, details):
    """One upload attempt; return only after a matching Telegram receipt."""
    info = await asyncio.to_thread(metadata, path, details)
    size = path.stat().st_size
    if info.get("format") != "FLAC" or not info.get("duration"):
        raise ValueError("Invalid FLAC output")
    cover = await asyncio.to_thread(thumbnail, path)
    try:
        with path.open("rb") as source:
            message = await bot.send_document(
                chat_id, document=source, filename=filename(path, info),
                caption=caption(info), thumbnail=cover, parse_mode=None,
                connect_timeout=30, read_timeout=180, write_timeout=180,
            )
        document = getattr(message, "document", None)
        if not document or not document.file_id or document.file_size != size:
            raise ValueError("Unconfirmed upload receipt")
    finally:
        if cover:
            cover.close()


async def stop_process(proc):
    if proc.returncode is None:
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), 5)
        except asyncio.TimeoutError:
            with suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            await proc.wait()


async def run_job(settings, bot, chat_id, url, status):
    jobs = settings.data / "jobs"
    jobs.mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="request-", dir=jobs))
    argv = [sys.executable, "-B", str(ROOT / "scripts/apple_worker.py"),
            "--cookies", str(settings.cookies), "--url", url, "--output", str(directory),
            "--codec", "flac", "--limit", "50", "--wrapper", settings.wrapper,
            "--wrapper-backend", settings.backend, "--decrypt-host", settings.decrypt_host,
            "--decrypt-port", str(settings.decrypt_port)]
    proc = None
    sent = kept = errors = 0
    completed = False
    last_status = 0.0
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
            env={key: os.environ[key] for key in ("PATH", "LANG", "HOME", "TMPDIR", "SSL_CERT_FILE") if key in os.environ},
        )
        while True:
            line = await asyncio.wait_for(proc.stdout.readline(), 600)
            if not line:
                break
            event = json.loads(line)
            kind = event.get("event")
            if kind == "stage" and time.monotonic() - last_status >= 5:
                with suppress(Exception):
                    await status.edit_text("Apple Music · " + str(event.get("stage", "working"))[:40])
                last_status = time.monotonic()
            elif kind == "track":
                path = managed_file(event["path"], directory)
                if path.suffix.lower() != ".flac":
                    raise ValueError("Non-FLAC output rejected")
                if path.stat().st_size >= UPLOAD_LIMIT:
                    retained = settings.data / "retained" / directory.name
                    retained.mkdir(parents=True, exist_ok=True)
                    destination = retained / path.relative_to(directory)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    await asyncio.to_thread(shutil.copyfile, path, destination)
                    # Verify durable bytes before acknowledging deletion of the working copy.
                    import hashlib
                    def digest(file):
                        with file.open("rb") as stream:
                            return hashlib.file_digest(stream, "sha256").digest()
                    if await asyncio.to_thread(digest, path) != await asyncio.to_thread(digest, destination):
                        raise ValueError("Retained copy verification failed")
                    await bot.send_message(chat_id, caption(event) + "\n\nAbove the upload limit. Original kept on the bot host under data/retained/.")
                    kept += 1
                else:
                    await deliver(bot, chat_id, path, event)
                    sent += 1
                proc.stdin.write(b"confirmed\n")
                await proc.stdin.drain()
            elif kind == "track_error":
                errors += 1
            elif kind == "error":
                raise RuntimeError("External service reported an error")
            elif kind == "done":
                completed = True
        code = await asyncio.wait_for(proc.wait(), 10)
        if code or not completed:
            raise RuntimeError("Worker did not finish")
        with suppress(Exception):
            await status.edit_text(f"Finished · {sent} sent · {kept} kept above the limit · {errors} failed")
        if not errors:
            with suppress(OSError):
                shutil.rmtree(directory)
    finally:
        if proc:
            await stop_process(proc)
        # Failure/cancellation leaves unconfirmed outputs in data/jobs/ for inspection.


def build_application(settings):
    app = Application.builder().token(settings.token).build()
    tasks = {}
    semaphore = asyncio.Semaphore(1)
    keyboard = ReplyKeyboardMarkup([["🍎 Download", "ℹ️ Help"], ["📋 Status", "✖️ Cancel"]], resize_keyboard=True)

    def authorized(update):
        return bool(update.effective_user and update.effective_chat and
                    update.effective_user.id in settings.allowed and update.effective_chat.type == "private")

    async def start(update, context):
        if authorized(update):
            await update.effective_message.reply_text("Samery · Apple Music\nSend one track, album or playlist link. FLAC uses the best available ALAC source.\n/cancel · /status", reply_markup=keyboard)

    async def status(update, context):
        if authorized(update):
            await update.effective_message.reply_text("Your request is queued or running." if update.effective_user.id in tasks else "No active request. Send an Apple Music link.")

    async def cancel(update, context):
        if authorized(update):
            task = tasks.get(update.effective_user.id)
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                tasks.pop(update.effective_user.id, None)
            await update.effective_message.reply_text("Request cancelled. Unconfirmed files are kept on the host." if task else "No active request.")

    async def request(update, context):
        if not authorized(update):
            return
        text = update.effective_message.text or ""
        if text in ("🍎 Download", "ℹ️ Help"):
            return await start(update, context)
        if text == "📋 Status":
            return await status(update, context)
        if text == "✖️ Cancel":
            return await cancel(update, context)
        uid = update.effective_user.id
        url = apple_url(text)
        if not url:
            await update.effective_message.reply_text("Send one music.apple.com track, album or playlist link.")
            return
        if uid in tasks or len(tasks) >= 10:
            await update.effective_message.reply_text("A request is already active or the queue is full. Use /status or /cancel.")
            return
        progress = await update.effective_message.reply_text("Queued · Best available lossless source")

        async def work():
            try:
                async with semaphore:
                    await run_job(settings, context.bot, update.effective_chat.id, url, progress)
            except asyncio.CancelledError:
                raise
            except Exception:
                with suppress(Exception):
                    await progress.edit_text("Request not completed. Check the service and your Telegram chat before retrying. Unconfirmed files are kept on the host; no automatic upload retry was made.")
            finally:
                tasks.pop(uid, None)
        tasks[uid] = asyncio.create_task(work())

    async def shutdown(application):
        pending = list(tasks.values())
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    async def error(update, context):
        # Never echo exception text, request URLs or account responses.
        return None

    app.post_stop = shutdown
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("apple", request))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, request))
    app.add_error_handler(error)
    return app


def main():
    logging.disable(logging.CRITICAL)
    try:
        settings = Settings.from_env()
        build_application(settings).run_polling(bootstrap_retries=0)
    except Exception:
        print("Startup failed. Check private settings, installed dependencies and network access.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
