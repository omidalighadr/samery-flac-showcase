# Setup

[← Project overview](../README.md)

## Prerequisites

- Python 3.12 and FFmpeg/FFprobe for local execution, or Docker Engine/Desktop with Compose.
- A new Telegram bot token from BotFather. Do not run a second polling app with an already-running bot's token.
- Numeric Telegram IDs for the users allowed to access your instance. Start a private chat with your bot first.
- Your own active Apple Music subscription and private Netscape-format cookie file.
- An independently configured compatible external Wrapper. This repository includes a protocol adapter, not the external service or account setup.

## Configure

From the repository root:

```sh
cp .env.example .env
mkdir -p private
```

Edit `.env` privately. Place your own cookie file at `private/apple-cookies.txt`; do not paste its contents into an issue or commit it.

| Variable | Meaning |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Your own BotFather token |
| `ALLOWED_USER_IDS` | Comma-separated numeric IDs; empty access lists are rejected |
| `APPLE_MUSIC_COOKIES` | Local cookie file path; Compose overrides this to its read-only mount |
| `APPLE_MUSIC_WRAPPER_URL` | Required external service URL |
| `APPLE_MUSIC_WRAPPER_BACKEND` | `v2` or `legacy-local` |
| `APPLE_MUSIC_DECRYPT_HOST` / `APPLE_MUSIC_DECRYPT_PORT` | Your compatible v2 service connection |
| `DATA_DIR` | Local job and retained-file directory; Compose uses a named volume |

The bot rejects incomplete configuration rather than opening access to everyone. Environment variables are loaded by your shell or Compose; Python does not implicitly load `.env`.

## Run locally

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r apple_music/requirements.txt
set -a
. ./.env
set +a
python apple_music/bot.py
```

Use `/start`, `/apple <link>`, `/status` or `/cancel` in a private chat. The interface is English. Send one link per message. One request per user and up to ten queued/running requests are accepted. Albums/playlists process at most 50 items per request in this reference app; it does not expose the private bot's full archive or resume interface.

## Run with Docker

```sh
docker compose up --build -d
docker compose ps
```

The container runs as UID/GID 65534. Its cookie-file mount must be readable by that container user while remaining protected on your host. The named `samery-data` volume stores generated files and retained outputs; inspect it before removing any volume. Do not use `docker compose down -v` if you need those files.

Use a compatible **v2** external service reachable from the container. `127.0.0.1` inside the container refers to the container itself; for a service on the host, configure its URL and decrypt host using `host.docker.internal` and the actual service ports. The service must accept that connection. The `legacy-local` adapter hardcodes loopback connections and is intended for local Python execution alongside its service, not the default isolated Compose network. A remote service also needs an appropriate private network and access controls.

The root Docker image now runs the bot continuously. It no longer runs the optional one-shot `toolkit/send_flac.py` command.

## File lifecycle

Files are sent as documents without re-encoding. The worker acknowledges successful uploads only after a Telegram document receipt has the expected size. Uploads are attempted once. An unknown network response can mean Telegram received the file; inspect the chat before resending the link.

Files smaller than 50 MiB are removed from the working directory after confirmed delivery. Larger files are copied to `data/retained/`, byte-hash verified and then removed from the working directory. Failed or cancelled jobs keep unconfirmed outputs in `data/jobs/`. They can consume disk space; this reference app has no automatic recovery command or old-job purge. Queue state is in memory and is lost on restart.

## Test without accounts

```sh
python -m pip install -r apple_music/requirements-test.txt
(cd apple_music && python -m pytest tests -q)
(cd toolkit && python -m unittest discover -s tests -v)
```

Tests do not require real tokens, cookies or downloads. The optional loopback test skips on environments that prohibit socket listeners. Hosted CI also builds the Docker image and imports the bot/third-party API without an account; it does not start polling or perform a live music download.

## Deployment limits

The public runtime targets GAMDL 3.9.1. The private application's patched dependency wheel is excluded. A clean install, even if it builds and imports successfully, may behave differently during actual account/media operations. No test here guarantees catalog availability, source resolution, external service readiness or uptime. The complete private assistant's channel publishing, databases and unrelated features are excluded.
