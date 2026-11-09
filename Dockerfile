FROM python:3.12-alpine

LABEL org.opencontainers.image.source="https://github.com/fjflima75/horizonarr" \
      org.opencontainers.image.description="New, upcoming and classic games, whether you can get them, one click to RetroArr" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/data PORT=8080
WORKDIR /app
COPY horizonarr ./horizonarr

RUN adduser -D -u 1000 horizonarr && mkdir -p /data && chown horizonarr /data
USER horizonarr
VOLUME /data
EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s --start-period=30s \
  CMD wget -qO- http://127.0.0.1:8080/health >/dev/null || exit 1

CMD ["python", "-m", "horizonarr"]
