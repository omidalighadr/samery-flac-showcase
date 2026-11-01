FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY apple_music/requirements.txt /app/apple_music/requirements.txt
RUN pip install --no-cache-dir -r apple_music/requirements.txt
COPY apple_music/ /app/apple_music/
RUN mkdir -p /app/data && chown 65534:65534 /app/data
USER 65534:65534
CMD ["python", "-B", "apple_music/bot.py"]
