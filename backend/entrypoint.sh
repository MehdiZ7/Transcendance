#!/bin/sh
set -e

# SECRET files
for name in $(env | sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)_FILE=.*/\1/p'); do
	eval "path=\${${name}_FILE}"
	if [ ! -r "$path" ]; then
		echo "FATAL: ${name}_FILE=$path cannot be read" >&2
		exit 1
	fi
	eval "export ${name}=\"\$(cat \"\$path\")\""
	unset "${name}_FILE"
done

if [ ! -w /srv/media ]; then
  echo "FATAL: /srv/media cannot be written" >&2
  exit 1
fi

echo "Migrations starting"
alembic upgrade head
echo "Migrations done"

if [ "$SEED_DEMO_DATA" = "true" ]; then
  echo "Data loading"
  python -m app.seeds
  echo "Data loaded"
fi

if [ "$UVICORN_RELOAD" = "true" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir /app/src \
    --ws-max-size "${WS_MAX_FRAME_BYTES:-4096}"
fi
# Realtime events live in process memory (LocalBackend): keep a single worker
# until a shared broker exists, or events published in one worker never reach
# sockets held by another.
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${UVICORN_WORKERS:-1}" \
    --ws-max-size "${WS_MAX_FRAME_BYTES:-4096}"
