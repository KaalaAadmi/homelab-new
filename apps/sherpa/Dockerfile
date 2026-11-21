FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY sherpa ./sherpa

# Runs as an unprivileged user. Uid 1000 matches the usual first user on the K8 Plus,
# so it can read ~/data/media (mounted read-only).
RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin sherpa
USER sherpa

EXPOSE 8320
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8320/health', timeout=4)" || exit 1
CMD ["python", "-m", "sherpa"]
