#!/bin/sh
set -e

CERT_DIR=/etc/nginx/certs
NAME="${SERVER_NAME:-localhost}"
PROJECT="${PROJECT}"

if [ ! -f "$CERT_DIR/server.crt" ]; then
  echo "No certification found — self signed certification generation for ${NAME}"
  mkdir -p "$CERT_DIR"
  openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout "$CERT_DIR/server.key" \
    -out    "$CERT_DIR/server.crt" \
    -subj   "/C=FR/O=${PROJECT}/CN=${NAME}" \
    -addext "subjectAltName=DNS:${NAME},DNS:localhost,IP:127.0.0.1"
  chmod 600 "$CERT_DIR/server.key"
else
  echo "Existing certification found (${CERT_DIR}/server.crt)"
fi
