# Build from the repository root:
#   docker compose -f example/docker-compose.yml up -d --build
#
# Your own campaign's image looks the same, with campaignlanding installed from a
# release tag instead of copied in, and your site/ and app.py in place of the
# example's.
FROM python:3.12-alpine

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY campaignlanding /app/campaignlanding
RUN pip install --no-cache-dir . gunicorn==23.0.0

COPY example/app.py /app/app.py
COPY example/site /app/site

# Never runs as root. docker-compose.yml overrides this with the host uid that
# owns the data volume; this is the fallback for anyone running the image bare.
RUN adduser -D -u 10001 campaign
USER campaign

ENV CAMPAIGN_SITE=/app/site \
    CAMPAIGN_DATA=/data \
    PYTHONUNBUFFERED=1

EXPOSE 8100

# One worker keeps the in-memory rate limiter honest. A page like this will never
# need more; if it somehow does, move the limiter to the proxy.
CMD ["gunicorn", "--bind", "0.0.0.0:8100", "--workers", "1", "--threads", "4", \
     "--access-logfile", "-", "--error-logfile", "-", "app:app"]
