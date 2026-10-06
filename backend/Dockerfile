# ---------- build ----------
FROM docker.io/library/python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# bytecode compile for build, faster
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# ---------- exec ----------
FROM docker.io/library/python:3.14-slim AS runtime

ARG UID=1001
ARG GID=1001

RUN groupadd -g ${GID} appuser \
 && useradd -u ${UID} -g ${GID} -m -s /usr/sbin/nologin appuser \
 && mkdir -p /app /srv/media \
 && chown appuser:appuser /app /srv/media /home/appuser \
 && chmod 755 /home/appuser

WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser . .

ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app/src PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8000

CMD ["./entrypoint.sh"]

FROM runtime AS dev

