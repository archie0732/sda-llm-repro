# Local web page for live Track V dialogues (scripts/live_web.py). Build context is filtered by .dockerignore:
# no third_party/, data/, results/, .env or keys in the image. Data and results are mounted at run time,
# see docker-compose.yml and README.
FROM python:3.12-slim

# opencv-python-headless needs libglib2.0-0 at import time
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY scripts ./scripts
RUN pip install --no-cache-dir ".[web]"

RUN useradd --create-home --uid 1000 sda && mkdir -p /app/results && chown sda:sda /app/results
USER sda

# Inside the container the server must listen on all interfaces so the port mapping can reach it. Who can reach
# the mapping is decided by docker-compose.yml, which publishes 127.0.0.1:8765 only.
ENV SDA_WEB_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1
EXPOSE 8765
CMD ["python", "scripts/live_web.py"]
