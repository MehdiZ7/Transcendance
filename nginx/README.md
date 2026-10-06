# nginx — Reverse proxy

The single entry point of the **Le Bon 42** stack. Every browser request goes
through this nginx container, which:

- **terminates TLS** (HTTPS, with a self-signed certificate generated on first
  start);
- **routes by path** to the API, the Next.js front, Grafana or the media
  files, all on one origin;
- **adds security headers**, including a Content-Security-Policy in
  production;
- **caps abuse** with per-IP rate limits and request body size limits;
- **compresses and caches** responses in production.

| Related topic | Document |
|---|---|
| Project overview | [`../README.md`](../README.md) |
| Backend API (routes, per-user rate limits, deployment checklist) | [`../backend/README.md`](../backend/README.md) |
| Real-time WebSocket protocol | [`../backend/src/app/core/realtime/README.md`](../backend/src/app/core/realtime/README.md) |
| Service definitions (ports, volumes, networks) | [`../docker-compose.yml`](../docker-compose.yml), [`../docker-compose.dev.yml`](../docker-compose.dev.yml) |

## Contents

- [At a glance](#at-a-glance)
- [Files](#files)
- [Where nginx sits](#where-nginx-sits)
- [Routing](#routing)
- [Running the proxy](#running-the-proxy)
- [Configuration templates](#configuration-templates)
- [TLS certificate](#tls-certificate)
- [Security headers](#security-headers)
- [Rate limiting](#rate-limiting)
- [Request body limits](#request-body-limits)
- [Compression and caching](#compression-and-caching)
- [Long-lived connections](#long-lived-connections)
- [Development and production configurations](#development-and-production-configurations)
- [Common tasks](#common-tasks)
- [Production checklist](#production-checklist)
- [Troubleshooting](#troubleshooting)
- [Known issues](#known-issues)

---

## At a glance

| Item | Value |
|---|---|
| Compose service | `proxy` |
| Base image | `nginx:1.30-alpine`, plus `openssl` for the certificate |
| Configuration | [`nginx.conf`](nginx.conf) under `make up`, [`nginx.dev.conf`](nginx.dev.conf) under `make dev` |
| Listens on (in the container) | `80` (HTTP, redirect only) and `443` (HTTPS, HTTP/2) |
| Published on (on the host) | `HTTP_PORT` → 80 and `HTTPS_PORT` → 443. `.env.example` sets `8080` and `8443` |
| Main URL | `https://localhost:8443` with the default `.env` |
| Volumes | `certs` → `/etc/nginx/certs` (read-write), `media` → `/srv/media` (read-only) |
| Network | `front` only: it reaches `api`, `web` and `grafana`, never the database or Prometheus |
| Starts after | `api` and `web` report healthy |
| Logs | `docker compose logs -f proxy` (access log, errors, rate-limit warnings) |

---

## Files

| File | Role |
|---|---|
| [`Dockerfile`](Dockerfile) | Three stages: `base` (nginx, openssl, the certificate script), `runtime` (production configuration) and `runtime-dev` (development configuration) |
| [`nginx.conf`](nginx.conf) | Production configuration **template**, used by `make up` |
| [`nginx.dev.conf`](nginx.dev.conf) | Development configuration **template**, used by `make dev` |
| [`entrypoint.sh`](entrypoint.sh) | Installed as `/docker-entrypoint.d/40-generate-cert.sh`. Creates a self-signed certificate when none exists |
| [`.dockerignore`](.dockerignore) | Keeps `certs/` and Markdown files (this README) out of the image |

> [!IMPORTANT]
> The two configuration files are copied **into the image** at build time.
> Editing them has no effect until the image is rebuilt: run `make up` or
> `make dev` again, which both rebuild what changed.

---

## Where nginx sits

```
                 host ports HTTP_PORT / HTTPS_PORT
                               │
browser ──HTTPS──▶  proxy (nginx) ── network "front" ──┬──▶ api:8000      FastAPI (REST, auth, WebSocket)
                    │                                  ├──▶ web:3000      Next.js front
                    │                                  └──▶ grafana:3000  dashboards
                    └── /srv/media (read-only volume, shared with the API)

network "backend" (not reachable from nginx): db, prometheus, postgres-exporter
```

- The front and the API share **one origin** (`https://localhost:8443`). Cookies
  are first-party, and the API needs no CORS.
- The front's server-side code calls the API directly on `http://api:8000`,
  **without** going through nginx. Those calls are not rate-limited by nginx.
- Grafana is reached only through nginx, under `/grafana/`: it publishes no host
  port. Prometheus is not reachable from outside at all: no host port, no
  route. Only Grafana queries it, on the `backend` network.

---

## Routing

nginx picks the location with the **longest matching prefix**. A request for
`/api/auth/login` therefore goes to `/api/auth/`, not `/api/`, and anything that
matches no other location goes to `/`, the front.

| Location | Sent to | Per-IP limit | Body cap | Purpose |
|---|---|---|---|---|
| `/api/ws` | `api:8000` (upstream `api_ws`) | `ws_per_ip` | 10 MB | Real-time WebSocket. Upgraded connection, 1-hour timeouts, no buffering |
| `/api/v1/uploads/` | `api:8000` | `upload_per_ip` | 6 MB | Image uploads, the only API route that takes a file |
| `/api/auth/` | `api:8000` | `auth_per_ip` | 64 KB | 42 login, OAuth callback, logout, email/password sign-up, login and password change |
| `/api/` | `api:8000` | `api_per_ip` | 64 KB | REST API (`/api/v1`), OpenAPI schema, Swagger UI, admin SSE stream |
| `/media/` | Files in `/srv/media` | — | — | Media files, served as downloads. Cached 7 days |
| `/_next/static/` | `web:3000` | — | — | Front build assets. Cached one year (`immutable`) |
| `/grafana/` | `grafana:3000` | — | 10 MB | Grafana. WebSocket-capable, 1-hour timeouts, no buffering |
| `= /grafana/login` | `grafana:3000` | `auth_per_ip` | 10 MB | Grafana's sign-in. Nested in `/grafana/`, whose settings it inherits |
| `= /grafana/metrics` | — | — | — | Grafana's own metrics: answers `404`. Nested in `/grafana/` |
| `/` | `web:3000` | `web_per_ip` | 10 MB | Front pages and Server Actions |

**Port 80** answers every request with a `301` redirect to
`https://<host>:<HTTPS_PORT><same path>`.

**Not routed:** the API's `/metrics` endpoint, Prometheus and the database. A
request for `/metrics` or `/prometheus/` reaches the front, which answers `404`.
Grafana's `/grafana/metrics` gets nginx's own `404`.

**Upstreams.** `proxy_pass` targets named `upstream` blocks:

| Upstream | Server | Keepalive connections |
|---|---|---|
| `api` | `api:8000` | 32 |
| `api_ws` | `api:8000` | none: an upgraded WebSocket connection cannot be reused |
| `web` | `web:3000` | 16 in production, none in development |
| `grafana` | `grafana:3000` | 16 |

Keepalive needs `proxy_http_version 1.1` and an empty `Connection` header,
which the HTTP locations set. The upstream host names are resolved **once, at
start**: see [Troubleshooting](#troubleshooting) for what that implies.

**Headers sent upstream.** Every proxied location but `/_next/static/`
forwards `Host`, `X-Real-IP`, `X-Forwarded-For` and `X-Forwarded-Proto`, so the
services know the original host, client address and scheme. The WebSocket
locations add `Upgrade` and `Connection`. `/` and `/grafana/` send `Host` as
`$http_host`, port included; the API locations send `$host`, without it.

---

## Running the proxy

The proxy is part of the stack; it is not meant to run on its own. From the
repository root:

| Command | Image stage | Configuration |
|---|---|---|
| `make dev` | `runtime-dev` | `nginx.dev.conf` |
| `make up` | `runtime` | `nginx.conf` |

### Environment variables

Set by [`../docker-compose.yml`](../docker-compose.yml) from `.env`:

| Variable | Default | Used for |
|---|---|---|
| `SERVER_NAME` | `localhost` | `server_name` of the HTTPS server, and the certificate's name |
| `HTTPS_PORT` | `443` (`8443` in `.env.example`) | The port in the HTTP → HTTPS redirect. Also the host port Compose publishes 443 on |
| `PROJECT` | `COMPOSE_PROJECT_NAME`, `lb42` | Organisation (`O=`) field of the generated certificate |
| `HTTP_PORT` | `80` (`8080` in `.env.example`) | Host port Compose publishes 80 on. Not read by nginx |

Rootless Podman cannot bind ports below 1024, hence `8080` and `8443` in
`.env.example`. With rootful Docker, set `80` and `443` to serve the standard
ports.

### Start-up sequence

The official nginx image runs the scripts in `/docker-entrypoint.d/` in order,
then starts `nginx -g 'daemon off;'`. Two of them matter here:

1. **`20-envsubst-on-templates.sh`** (from the image) renders
   `/etc/nginx/templates/default.conf.template` into
   `/etc/nginx/conf.d/default.conf`, replacing the environment variables. See
   [Configuration templates](#configuration-templates).
2. **`40-generate-cert.sh`** (our [`entrypoint.sh`](entrypoint.sh)) creates a
   self-signed certificate if `/etc/nginx/certs/server.crt` does not exist.
   See [TLS certificate](#tls-certificate).

The other scripts (`10-…`, `15-…`, `30-…`) come with the image and change
nothing in this setup. These steps run on **every** container start, not
only the first.

### Health

- **Start order.** Compose starts the proxy only once `api` and `web` report
  healthy.
- **Healthcheck.** Every 10 seconds, `wget` fetches `https://127.0.0.1/`
  inside the container. That request is proxied to the front, so the proxy is
  healthy only when nginx **and** the front answer.

---

## Configuration templates

`nginx.conf` and `nginx.dev.conf` are not used as they are: they are
**templates**. At container start, `envsubst` replaces `${SERVER_NAME}` and
`${HTTPS_PORT}` with their values from the environment:

```nginx
return 301 https://$host:${HTTPS_PORT}$request_uri;   # template
return 301 https://$host:8443$request_uri;            # rendered, with HTTPS_PORT=8443
```

`envsubst` replaces **only variables that exist in the container's
environment**. nginx's own variables (`$host`, `$request_uri`,
`$http_upgrade`…) are left alone, because no environment variable has those
lowercase names.

Rules when editing a template:

- **Write template variables as `${NAME}`, in upper case**, like the existing
  ones.
- **Pass every new one to the container**, in the `proxy` `environment:` block
  of `docker-compose.yml`. A placeholder with no matching variable is left as
  is, and nginx then refuses to start with `unknown "NAME" variable`.
- **Never give an environment variable the name of an nginx variable**: it
  would be substituted into the configuration.
- **Check the result** with `docker compose exec proxy nginx -T`, which prints
  the rendered configuration.

---

## TLS certificate

### The generated certificate

On start, [`entrypoint.sh`](entrypoint.sh) checks for
`/etc/nginx/certs/server.crt`. If it is missing, it generates:

| Property | Value |
|---|---|
| Type | Self-signed, RSA 2048 |
| Validity | 825 days |
| Subject | `CN=<SERVER_NAME>`, `O=<PROJECT>`, `C=FR` |
| Alternative names | `DNS:<SERVER_NAME>`, `DNS:localhost`, `IP:127.0.0.1` |
| Files | `server.crt`, and `server.key` (mode `600`) |

The files live in the `certs` volume, so the same certificate is reused across
restarts and rebuilds. Browsers show a warning for it once; accept it to
continue. With curl, pass `-k`.

### Trusting it on your machine (optional)

To avoid the warning and `-k`, export the certificate and trust it:

```bash
docker compose cp proxy:/etc/nginx/certs/server.crt ./lb42-dev.crt
curl --cacert lb42-dev.crt https://localhost:8443/api/v1/health
```

Import `lb42-dev.crt` into your browser's or system's trusted certificates to
remove the browser warning. With Podman, use `podman cp` with the container
name shown by `make ps`.

### Regenerating it

The certificate is never regenerated while `server.crt` exists, even after
`SERVER_NAME` changes. To get a new one, delete it and restart the proxy:

```bash
docker compose exec proxy rm /etc/nginx/certs/server.crt /etc/nginx/certs/server.key
docker compose restart proxy
```

Alternatively, after `make down`, delete the whole volume with
`docker volume rm lb42_certs`.

### Using a real certificate

nginx uses whatever `server.crt` and `server.key` it finds in the `certs`
volume. To serve a trusted certificate:

```bash
docker compose cp fullchain.pem proxy:/etc/nginx/certs/server.crt   # certificate + intermediates
docker compose cp privkey.pem   proxy:/etc/nginx/certs/server.key
docker compose exec proxy nginx -s reload
```

- `server.crt` must contain the full chain: the certificate first, then the
  intermediate certificates.
- Port 80 redirects every request, so HTTP-01 challenges (such as Let's
  Encrypt's default) cannot be answered as is. Obtain the certificate another
  way, for example with a DNS challenge.
- Once the certificate is trusted, enable HSTS: see
  [Production checklist](#production-checklist).

### TLS settings

| Setting | Value |
|---|---|
| Protocols | TLS 1.2 and TLS 1.3 |
| Ciphers | `HIGH:!aNULL:!MD5` |
| Session cache | Shared, 10 MB, sessions kept 1 day |
| HTTP/2 | On |

---

## Security headers

### Headers on every response

| Header | Value | Protects against | Production | Development |
|---|---|---|---|---|
| `X-Content-Type-Options` | `nosniff` | The browser guessing a different content type (for example running a text file as a script) | Yes | Yes |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Leaking full URLs to other sites | Yes | Yes |
| `Permissions-Policy` | `geolocation=(), camera=(), microphone=()` | Pages using the location, camera or microphone | Yes | Yes |
| `Content-Security-Policy` | See below | Cross-site scripting, clickjacking, data exfiltration | Yes | **No** |
| `Strict-Transport-Security` | `max-age=31536000` | Downgrade to HTTP | **Commented out** | No |

### Content-Security-Policy (production)

| Directive | Value | Meaning |
|---|---|---|
| `default-src` | `'self'` | By default, load resources only from this site |
| `script-src` | `'self' 'unsafe-inline'` | Scripts from this site. Inline scripts are allowed because Next.js emits them |
| `style-src` | `'self' 'unsafe-inline'` | Styles from this site, inline styles allowed |
| `img-src` | `'self' data: blob: https://cdn.intra.42.fr` | Images from this site, inline images, and 42 profile pictures |
| `font-src` | `'self'` | Fonts from this site only |
| `connect-src` | `'self' wss://$host` | `fetch` and WebSocket to this site only. Current browsers include same-origin `wss://` in `'self'`; `wss://$host` covers the default port |
| `frame-ancestors` | `'none'` | No other site may embed these pages in a frame (clickjacking) |
| `base-uri` | `'self'` | A `<base>` tag cannot redirect relative URLs elsewhere |
| `object-src` | `'none'` | No plugins (`<object>`, `<embed>`) |

What this means in practice:

- **External scripts and styles are blocked**, CDNs included. This is why
  Swagger UI, which loads its assets from `cdn.jsdelivr.net`, stays blank under
  `make up`.
- **Images from other hosts are blocked**, unless they come through Next.js's
  image optimizer (`/_next/image`), which serves them from the site itself.
- **The header value must stay on one line.** A line break inside it produces
  an invalid header.
- **Grafana has its own copy**, in `/grafana/`, with `data:` added to
  `connect-src`: Grafana's pages fetch a `data:` URL, which the server-level
  policy refuses.

### How `add_header` is inherited

> [!WARNING]
> nginx applies the server-level `add_header` directives to a location **only
> if that location has no `add_header` of its own**. As soon as a location
> adds one header, it loses all the others.

That is why `/media/` and `/_next/static/` repeat the security headers next to
their caching headers, and `/grafana/` next to its own CSP. When you add an `add_header` to a location, repeat the
baseline headers there too, and in production the CSP when the location
serves pages or scripts.

---

## Rate limiting

nginx limits requests **per client IP address**. It is a coarse first line of
defence; the API applies finer limits per signed-in user (see
[`../backend/README.md`](../backend/README.md#rate-limiting-per-user)).

| Zone | Applied to | Sustained rate | Burst |
|---|---|---|---|
| `api_per_ip` | `/api/` | 100 requests/s | 200 |
| `auth_per_ip` | `/api/auth/` (42 login, callback, logout, email/password routes), `/grafana/login` | 30 requests/min | 20 |
| `ws_per_ip` | `/api/ws` (handshakes only, not the messages) | 10 requests/s | 20 |
| `upload_per_ip` | `/api/v1/uploads/` (image uploads) | 60 requests/min | 20 |
| `web_per_ip` | `/` (front pages) | 100 requests/s | 200 |

`/_next/static/`, `/media/` and the rest of `/grafana/` are not limited.
Grafana's sign-in shares the `auth_per_ip` bucket with the app's.

**How a zone works.** Requests up to the sustained rate always pass. A client
may also send up to *burst* extra requests at once, which are served
immediately (`nodelay`). Beyond that, nginx answers at once with:

```http
HTTP/2 429
Content-Type: application/json
Retry-After: 1

{"detail":"Too many requests, slow down"}
```

The JSON body has the same shape as the API's own errors, so the front can
handle both the same way. A `429` produced by the API itself passes through
unchanged, with its own `Retry-After`. Each refusal is logged as a warning:
`limiting requests, excess: … by zone "api_per_ip", client: …`.

**Why the values are high.** An IP address is not a person:

- behind rootless Podman, every browser reaches nginx from the same address
  (the network gateway), so a zone becomes a limit for **all users together**;
- on a campus, many students share one public address.

If a demo with many users at once gets `429` responses, raise the zone in
question first, starting with `auth_per_ip`. See
[Common tasks](#change-a-rate-limit-or-a-body-cap).

Each zone keeps its counters in 10 MB of shared memory, enough for about
80 000 addresses.

---

## Request body limits

| Where | Maximum body | Why |
|---|---|---|
| `/api/` and `/api/auth/` | **64 KB** | Apart from uploads the API accepts JSON only, and its largest legitimate body (a listing) is about 15 KB. See [`backend/src/app/schemas/limits.py`](../backend/src/app/schemas/limits.py) |
| `/api/v1/uploads/` | **6 MB** | The API refuses images over 5 MB itself (`MAX_UPLOAD_BYTES`); this outer cap leaves room for the multipart overhead |
| Everywhere else | **10 MB** | The front: Next.js Server Actions accept up to 8 MB (`bodySizeLimit` in [`front/next.config.ts`](../front/next.config.ts)) |

A larger body is refused with `413 Request Entity Too Large`, before it reaches
the service. This error page is nginx's default **HTML** page, not JSON.

---

## Compression and caching

### Compression (production only)

| Setting | Value |
|---|---|
| Types | HTML, plain text, CSS, JSON, JavaScript, XML, SVG |
| Minimum size | 1 KB |
| Level | 5 (of 9) |
| Proxied responses | Compressed too (`gzip_proxied any`) |
| `Vary: Accept-Encoding` | Sent, so caches keep compressed and plain copies apart |

The development configuration does not compress.

### Caching

| Location | Headers | Why |
|---|---|---|
| `/_next/static/` | `Cache-Control: public, max-age=31536000, immutable` | Next.js puts a content hash in these file names: a new build means new URLs, so a file can be cached forever |
| `/media/` | Expires in 7 days, `Cache-Control: public`, `Content-Disposition: attachment` | Media rarely change. `attachment` makes the browser download a file instead of displaying it, so a malicious file cannot run as a page on this origin |

Other responses carry no caching headers from nginx; the services decide.

---

## Long-lived connections

| Connection | Location | Read/send timeout | Buffering | Kept alive by |
|---|---|---|---|---|
| Real-time WebSocket | `/api/ws` | 1 hour | Off | The front's ping every 25 seconds |
| Admin dashboard SSE stream | `/api/` (`/api/v1/analytics/stream`) | 60 seconds (nginx default) | Off for this response only, through the API's `X-Accel-Buffering: no` | The API's comment line every 20 seconds |
| Grafana live updates | `/grafana/` | 1 hour | Off | Grafana |

- **WebSocket upgrade.** The `map $http_upgrade $connection_upgrade` block at
  the top of the files sets `Connection: upgrade` when the browser asks for a
  WebSocket, and `Connection: close` otherwise.
- **Timeouts.** A connection that stays silent longer than its read timeout is
  closed by nginx. Any new long-lived endpoint under `/api/` must send
  something at least every 60 seconds, or get its own location with a longer
  timeout.

---

## Development and production configurations

The two files are identical except for these points:

| Aspect | `nginx.conf` (`make up`) | `nginx.dev.conf` (`make dev`) | Reason |
|---|---|---|---|
| Content-Security-Policy | On (server level, `/_next/static/` and `/grafana/`) | Off | Development tools and Swagger UI's CDN assets must load |
| `/grafana/` → security headers | Repeated, next to Grafana's own CSP | Inherited from the server level | An `add_header` in a location drops the inherited ones |
| `/grafana/` → `Host` header | `$http_host` (port kept) | `$host` (port dropped) | — |
| HSTS | Present, commented out | Absent | Needs a trusted certificate |
| gzip | On | Off | Faster local iterations |
| `/` → WebSocket upgrade | No | Yes | Next.js hot reload uses a WebSocket |
| `/` → buffering | On (default) | Off | Development responses stream |
| `web` upstream keepalive | 16 | None | — |

> [!IMPORTANT]
> Any other change (a route, a rate limit, a body cap, a header, TLS) must be
> made in **both** files, or development and production will drift apart.

---

## Common tasks

### Apply a configuration change

1. Edit `nginx.conf` and, unless the change is about one of the
   [differences](#development-and-production-configurations), `nginx.dev.conf`.
2. Rebuild and restart the proxy: `make up`, or stop and rerun `make dev`.
3. Check the result:

   ```bash
   docker compose exec proxy nginx -t     # syntax and references are valid
   docker compose exec proxy nginx -T     # print the rendered configuration
   docker compose logs -f proxy           # watch requests and errors
   ```

To experiment without rebuilding, edit `/etc/nginx/conf.d/default.conf`
inside the container, then run `nginx -t` and `nginx -s reload`. The change
is lost when the container is recreated.

### Add a route to a new service

1. **Network.** Attach the service to the `front` network in
   `docker-compose.yml`: nginx can reach nothing else.
2. **Upstream and location.** Add both to `nginx.conf` and `nginx.dev.conf`.
   A template (`docs` is a placeholder):

   ```nginx
   upstream docs {
   	server docs:8080;
   	keepalive 16;
   }

   # inside the HTTPS server block
   location /docs/ {
   	limit_req							zone=web_per_ip burst=200 nodelay;

   	proxy_pass							http://docs;
   	proxy_http_version					1.1;

   	proxy_set_header Connection			"";
   	proxy_set_header Host				$host;
   	proxy_set_header X-Real-IP			$remote_addr;
   	proxy_set_header X-Forwarded-For	$proxy_add_x_forwarded_for;
   	proxy_set_header X-Forwarded-Proto	$scheme;
   }
   ```

3. **Path prefix.** `proxy_pass http://docs;` (no trailing slash) forwards the
   full path, `/docs/page`. `proxy_pass http://docs/;` strips the prefix and
   forwards `/page`. Pick the one the service expects: Grafana, for example,
   is configured to live under `/grafana/` and receives the full path.
4. **Limits and headers.** Choose a rate-limit zone and a body cap. If the
   location sets any `add_header`, repeat the security headers (see
   [How `add_header` is inherited](#how-add_header-is-inherited)).
5. **Start order.** nginx refuses to start if an upstream host name cannot be
   resolved. Add the service to the proxy's `depends_on`, or make sure it
   always runs.
6. **Rebuild and test** with `nginx -t` and a `curl -k` on the new path.

### Change a rate limit or a body cap

- **Rate:** edit the `limit_req_zone` line (`rate=`) at the top of the file.
  **Burst:** edit the `limit_req` line in the location.
- **Body cap:** edit `client_max_body_size` in the location, or at server level
  for the default.
- Make the change in both files, then rebuild. If you raise the API's body cap,
  check the API's own field limits too.

### Allow a new external source in the CSP

1. In `nginx.conf`, add the origin (for example `https://cdn.example.org`) to
   the right directive (`img-src`, `script-src`, `connect-src`…).
2. Do it in **all three** places the header appears: the server level,
   `/_next/static/` and `/grafana/`.
3. Keep the value on one line, rebuild, and check the browser console for
   `Refused to load` messages.

### Read the logs

```bash
docker compose logs -f proxy
```

The access log uses nginx's standard format (client address, request, status,
size, referrer, user agent). Errors and rate-limit warnings appear in the same
stream.

---

## Production checklist

The nginx part of a deployment on a real host. The backend's
[Deployment checklist](../backend/README.md#deployment-checklist) covers the
rest.

- [ ] **Host name and ports.** In `.env`, set `SERVER_NAME` to the public host
      name and, with rootful Docker, `HTTP_PORT=80` and `HTTPS_PORT=443`.
- [ ] **Certificate.** Install a trusted certificate in the `certs` volume
      (see [Using a real certificate](#using-a-real-certificate)), or at least
      regenerate the self-signed one for the new `SERVER_NAME`.
- [ ] **HSTS.** Once the certificate is trusted, uncomment the
      `Strict-Transport-Security` line in `nginx.conf`. Browsers then refuse
      plain HTTP for a year: consider a short `max-age` first.
- [ ] **Monitoring access.** Grafana is public under `/grafana/`, protected only
      by its own sign-in: keep the generated `secrets/GRAFANA_PASSWORD` (or
      replace it with a strong one before the first start). Do not add a route
      or a host port for Prometheus, which has no authentication.
- [ ] **Rate limits.** If the public traffic comes through a load balancer or
      a NAT, every client shares its address: adjust the zones.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| The browser warns that the connection is not private | The certificate is self-signed | Accept it once, [trust it](#trusting-it-on-your-machine-optional), or install a real one |
| The certificate shows an old host name | The existing certificate is reused after `SERVER_NAME` changed | [Regenerate it](#regenerating-it) |
| `make dev` hangs before the proxy starts | The proxy waits for `api` and `web` to be healthy | Check `make ps` and `docker compose logs api web`. The front can take up to two minutes to compile in development |
| The proxy exits with `host not found in upstream "grafana:3000"` (or `api`, `web`) | Upstream names are resolved at start, and that container is not running | Start the whole stack with `make up` or `make dev` |
| `502 Bad Gateway` | The service behind is down or restarting (the API reloading, the front compiling), or it was recreated with a new address that nginx does not know | Check that service's logs. If it runs fine, `docker compose restart proxy` |
| `504 Gateway Timeout` | The service took more than 60 seconds to answer | Find the slow request in the service's logs |
| `429` with `{"detail":"Too many requests, slow down"}` and `Retry-After: 1` | Per-IP limit. Under rootless Podman, all users share one address | Raise the zone, `auth_per_ip` first. See [Rate limiting](#rate-limiting) |
| `413 Request Entity Too Large` (HTML page) | The body exceeds 64 KB on `/api/`, or 10 MB elsewhere | Send less, or raise the cap. See [Request body limits](#request-body-limits) |
| nginx refuses to start with `unknown "NAME" variable` | A `${NAME}` placeholder has no matching environment variable | Add `NAME` to the proxy's `environment:` in `docker-compose.yml`. See [Configuration templates](#configuration-templates) |
| A configuration edit has no effect | The templates are baked into the image, or you edited the other file | Rebuild with `make up` or `make dev`. `make dev` uses `nginx.dev.conf` |
| Swagger UI is blank, or a script, style or image is blocked under `make up` | The production CSP | Read the `Refused to load` message in the browser console, then [allow the source](#allow-a-new-external-source-in-the-csp) if it is legitimate |
| The HTTP → HTTPS redirect goes to the wrong port | `HTTPS_PORT` changed but the proxy was not recreated: the template is rendered at start | Run `make up` (or rerun `make dev`) |
| `bind: permission denied` on port 80 or 443 | Rootless Podman cannot bind ports below 1024 | Keep `HTTP_PORT=8080` and `HTTPS_PORT=8443` |

---

## Known issues

- **HSTS is disabled** until a trusted certificate is installed.
- **Some responses lack the CSP header** in production: files under `/media/`
  and nginx's own `429` page set their own headers, so they do not inherit it.
  Media files are served as downloads, which limits the impact.
- **Upstream addresses are resolved once, at start.** A service recreated
  with a new address answers `502` until the proxy restarts.
