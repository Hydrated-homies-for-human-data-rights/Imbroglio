# Imbroglio pipeline + demo console.
# Build from pipeline/:   docker build -t imbroglio .
# Run:  docker run -p 8765:8765 -e IMBROGLIO_PASSWORD=... -e DATABASE_URL=... imbroglio

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Shared browser location so the non-root user below can run Chromium.
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt .
# `playwright install` fetches the Chromium build matching the installed
# playwright package (an image-pinned browser can drift from requirements.txt);
# --with-deps adds the system libraries Chromium needs on Debian.
RUN pip install -r requirements.txt \
 && playwright install --with-deps chromium \
 && apt-get update && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/*

COPY imbroglio/ imbroglio/
COPY demo/ demo/

# Never run a browser that loads arbitrary websites as root.
RUN useradd --create-home --uid 10001 app
USER app

# Railway injects PORT; HOST must be public inside the container. app.py
# refuses to start on a public interface unless IMBROGLIO_PASSWORD is set.
ENV HOST=0.0.0.0 PORT=8765
EXPOSE 8765

# tini as PID 1 reaps exited Chromium helper processes; without it they
# piled up as zombies under the Python server.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "demo/app.py"]
