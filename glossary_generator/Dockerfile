# Glossary Suggester — container image
#
# Slim base, no compiler: we use psycopg2-binary (wheels), so there is no need for
# gcc/g++/unixodbc-dev. If you switch to source psycopg2 or add pyodbc, reintroduce
# the build deps for those drivers only.
FROM python:3.12-slim

WORKDIR /app

# Dependencies first for layer caching. gunicorn is in requirements.txt.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# Non-root user, plus a writable /data dir for runtime state (people/connections/
# settings/glossaries JSON). The app already takes these paths from env, so we just
# point them at the mounted volume below.
RUN useradd -m appuser && mkdir -p /data && chown -R appuser:appuser /app /data
USER appuser

ENV HOST=0.0.0.0 \
    PORT=5000 \
    GLOSSARY_PEOPLE=/data/people.json \
    GLOSSARY_CONNECTIONS=/data/connections.json \
    GLOSSARY_SETTINGS=/data/settings.json \
    GLOSSARY_GLOSSARIES=/data/glossaries.json

EXPOSE 5000

# Liveness via the /health endpoint (stdlib only — no curl in slim image).
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:5000/health',timeout=3).status==200 else 1)" || exit 1

# Threaded worker (-k gthread) so the NDJSON/SSE streaming endpoints
# (/api/apply-to-pdc-stream, /api/pdc-profiling, /api/pull-model) can run
# concurrently; generous timeout because enrichment + PDC apply are long-running.
CMD ["gunicorn", "-k", "gthread", "--threads", "8", "--timeout", "120", \
     "-b", "0.0.0.0:5000", "app:app"]
