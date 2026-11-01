FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY toolkit/ /app/
USER 65534:65534
ENTRYPOINT ["python", "send_flac.py"]
