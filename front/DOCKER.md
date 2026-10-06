# Docker

Base image: [node:22-alpine3.24](https://hub.docker.com/layers/library/node/22-alpine3.24/images/sha256-76789712cd1ae89a1225eac9077010d68987a423588042dac30446f502f1858c)

The `Dockerfile` (in `front/`) is a multi-stage build:

```
base ──▶ dependencies ──┬──▶ development
                        └──▶ builder ─(build output)─┐
base ──────────────────────────────────────────────▶ production
```

- `base` — sets the base image (`node:22-alpine3.24`), the `WORKDIR /app` and disables Next telemetry.
- `dependencies` — from `base`: copies `package.json` / `package-lock.json` then runs `npm ci` (reproducible install).
- `development` — from `dependencies`: copies all the code, `NODE_ENV=development`, runs `npm run dev` on `0.0.0.0` (hot reload).
- `builder` — from `dependencies`: `NODE_ENV=production`, takes `NEXT_PUBLIC_API_URL` as a build argument (default `/api/v1`, baked into the browser bundle), copies the code then runs `npm run build`.
- `production` — from `base`: keeps only the build artifacts (`public`, `.next/standalone`, `.next/static`), creates a non-root `nextjs` user (UID 1001) and runs `node server.js`.

The build is done with the `--target` matching the desired stage.

## In the stack

Normally you never build this image by hand: Compose builds it as the `web`
service from the repository root.

| Command | Target | Notes |
|---|---|---|
| `make up` | `production` | `API_INTERNAL_URL=http://api:8000/api/v1` for server-side calls |
| `make dev` | `development` | `front/` is bind-mounted into `/app`, with `node_modules` and `.next` kept in volumes |

## Build by hand

```bash
# Dev
docker build --target development -t front-dev front

# Prod
docker build --target production -t front-prod front
```

## Run by hand

```bash
# Dev
docker run --rm -it -p 3000:3000 front-dev

# Prod
docker run --rm -p 3000:3000 front-prod
```

Run alone, the container has no API behind it: pages that load data fail.
Use it to check that the image builds and starts; use `make dev` to work on
the application.
