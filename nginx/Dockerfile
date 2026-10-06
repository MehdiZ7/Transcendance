FROM docker.io/library/nginx:1.30-alpine AS base

RUN apk add --no-cache openssl

COPY --chmod=0755 entrypoint.sh /docker-entrypoint.d/40-generate-cert.sh

FROM base AS runtime

# COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/templates/default.conf.template
#the image's 20-envsubst-on-templates.sh renders it to /etc/nginx/conf.d/default.conf at start, overwriting the stock one

# exec dev: nginx as a proxy in front of the server
FROM base AS runtime-dev

# COPY nginx.dev.conf /etc/nginx/conf.d/default.conf
COPY nginx.dev.conf /etc/nginx/templates/default.conf.template
#the image's 20-envsubst-on-templates.sh renders it to /etc/nginx/conf.d/default.conf at start, overwriting the stock one
