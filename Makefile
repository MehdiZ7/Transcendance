
# `docker` is a real Docker Engine on some machines and a rootless Podman
# shim on others (notably 42 campus machines, which have no daemon/root
# access). Detect which one we're actually talking to and, for Podman,
# layer docker-compose.podman.yml on top to fix its rootless-specific
# quirks (see that file) — so `make dev`/`make up` work unmodified either way.
PODMAN_OVERRIDE := $(shell docker --version 2>/dev/null | grep -qi podman && echo "-f docker-compose.podman.yml")
COMPOSE = docker compose -f docker-compose.yml $(PODMAN_OVERRIDE)
COMPOSE_DEV = $(COMPOSE) -f docker-compose.dev.yml

SECRET_FILES =	secrets/POSTGRES_USER secrets/POSTGRES_PASSWORD secrets/SECRET_KEY \
				secrets/FT_CLIENT_ID secrets/FT_CLIENT_SECRET \
				secrets/GRAFANA_USER secrets/GRAFANA_PASSWORD

# UID/GID baked into the api image and used to run it in dev
# rootless user namespace maps only container ids 0 and 1..65536, so a host id
# outside that range (e.g. 44522941 from 42 LDAP) cannot be chown'd during
# a build => Fall back to 1001, which is the Dockerfile default
export UID := $(shell id -u | awk '{ if ($$1 >= 1000 && $$1 <= 60000) print $$1; else print 1001 }')
export GID := $(shell id -g | awk '{ if ($$1 >= 1000 && $$1 <= 60000) print $$1; else print 1001 }')

BUILD_INPUTS		:= backend front nginx docker-compose.yml docker-compose.dev.yml docker-compose.podman.yml
BUILD_HASH 			= $(shell git ls-files -co --exclude-standard -z -- $(BUILD_INPUTS) \
					| xargs -0 sha1sum 2>/dev/null | sha1sum | cut -d ' ' -f1 )
BUILD_STAMP 		:= .build_stamp
BUILD_STAMP_DEV 	:= .build_stamp_dev

.DEFAULT_GOAL 		:= all
.env:
	@cp .env.example $@ && chmod 600 $@ \
	&& echo ".env created based on .env.example"

secrets/POSTGRES_USER:
	@mkdir -p secrets && chmod 700 secrets \
	&& printf 'lb42' > $@ && chmod 644 $@ \
	&& echo "$@ created"

secrets/POSTGRES_PASSWORD:
	@mkdir -p secrets && chmod 700 secrets \
	&& openssl rand -hex 24 | tr -d '\n' > $@ \
	&& chmod 644 $@ \
	&& echo "$@ generated"

secrets/SECRET_KEY:
	@mkdir -p secrets && chmod 700 secrets \
	&& openssl rand -hex 32 | tr -d '\n' > $@ \
	&& chmod 644 $@ \
	&& echo "$@ generated"

secrets/GRAFANA_USER:
	@mkdir -p secrets && chmod 700 secrets \
	&& printf 'lb42' > $@ && chmod 644 $@ \
	&& echo "$@ created"

secrets/GRAFANA_PASSWORD:
	@mkdir -p secrets && chmod 700 secrets \
	&& openssl rand -hex 24 | tr -d '\n' > $@ \
	&& chmod 644 $@ \
	&& echo "$@ generated"

FT_SECRETS = secrets/FT_CLIENT_ID secrets/FT_CLIENT_SECRET

# An empty file counts as missing: the rule runs again until it is filled in.
.PHONY: $(foreach f,$(FT_SECRETS),$(if $(shell test -s $(f) && echo ok),,$(f)))

# Cannot be generated: both come from the app registered on the 42 intra.
# Prompted when missing or empty if run from a terminal; otherwise left empty
# so `make up` does not fail, and auth stays off until filled in.
$(FT_SECRETS):
	@mkdir -p secrets && chmod 700 secrets \
	&& : > $@ && chmod 644 $@ \
	&& if [ -t 0 ]; then \
		printf "%s (paste from https://profile.intra.42.fr/oauth/applications, empty to skip): " "$(@F)"; \
		trap "stty echo" EXIT INT TERM; stty -echo; IFS= read -r value || value=; stty echo; echo; \
		printf "%s" "$$value" > $@; \
	fi \
	&& if [ -s $@ ]; then echo "$@ saved"; \
	else echo "$@ is empty - paste the value from https://profile.intra.42.fr/oauth/applications"; fi

all: up

up: $(BUILD_STAMP)
	$(COMPOSE) up -d

dev: $(BUILD_STAMP_DEV)
	$(COMPOSE_DEV) up

.build_hash: FORCE
	@h='$(BUILD_HASH)'; echo "$$h" | cmp -s - $@ || echo "$$h" > $@
FORCE:

RECREATE := $(if $(PODMAN_OVERRIDE),--force-recreate)

$(BUILD_STAMP): .build_hash .env | $(SECRET_FILES)
	rm -f $(BUILD_STAMP_DEV)
	$(COMPOSE) build
	$(COMPOSE) up -d --no-start $(RECREATE)
	touch $@

$(BUILD_STAMP_DEV): .build_hash .env | $(SECRET_FILES)
	rm -f $(BUILD_STAMP)
	$(COMPOSE_DEV) build
	$(COMPOSE_DEV) up -d --no-start $(RECREATE)
	touch $@

down:
	$(COMPOSE_DEV) down --remove-orphans

clean:
	$(COMPOSE_DEV) down -v --remove-orphans
	rm -f $(BUILD_STAMP) $(BUILD_STAMP_DEV)

# Images only named in a Dockerfile (FROM / COPY --from with a registry path):
# no service refers to them, so `down --rmi all` never sees them.
BASE_IMAGES = $(shell sed -nE 's/^(FROM|COPY) +(--from=)?([^ ]+\/[^ ]+).*/\3/p' $(wildcard */Dockerfile) | sort -u)

# Removes every image this project uses (pulled and base ones included), so the
# next build pulls them all again. Scoped to lb42, except the dangling prune.
# Why: on 42 machines the images live in /goinfre, and the ones stored before a
# login come back with all their files owned by root. Fresh volumes inherit that
# ownership and non-root services (api, prometheus, grafana) cannot write to them.
# Dangling images go before the base ones: a base image that still has children
# is only untagged, and its layers would be reused as is by the next pull.
fclean: 
	-$(COMPOSE_DEV) down -v --rmi all --remove-orphans
	rm -f $(BUILD_STAMP) $(BUILD_STAMP_DEV)
	-docker image prune -f
	-docker rmi -f $(BASE_IMAGES)

re: fclean all

# Clears build cache and dangling images (tries podman, falls back to docker).
# DANGER: not scoped to this project — wipes cache/images/stopped containers
# for every container project on this machine, not just lb42.
prune:
	-podman system prune --build -f 2>/dev/null || docker builder prune -f 2>/dev/null || true
	-docker image prune -f

ps:
	@$(COMPOSE) ps

logs:
	@$(COMPOSE) logs -f

# Backend tests - throwaway Postgres on its own port/container - never touches the dev/prod db.
# rm first because a failed migration aborts the recipe with lb42_test_db still running, which also block the enxt make test with lb42_test_db already in use
test:
	@docker rm -f lb42_test_db >/dev/null 2>&1 || true
	@docker run -d --rm --name lb42_test_db \
		-e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=lebon42_test \
		-p 127.0.0.1:5433:5432 \
		docker.io/library/postgres:18-alpine >/dev/null
	@until docker exec lb42_test_db pg_isready -U postgres >/dev/null 2>&1; do sleep 0.5; done
	cd backend \
	&& export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_DB=lebon42_test \
	&& uv run alembic upgrade head \
	&& uv run pytest; \
	status=$$?; \
	docker stop lb42_test_db >/dev/null; \
	exit $$status

test_ws:
	cd backend && POSTGRES_USER=x POSTGRES_PASSWORD=x uv run pytest tests/test_ws

test_ws_live:
	cd backend && POSTGRES_USER=x POSTGRES_PASSWORD=x uv run python tests/live/realtime/server.py
test_ws_live_shutdown:
	pkill -f tests/live/realtime/server.py

# curl tests of /api/auth/* against the running stack (make up or make dev
# first). Interactive: the 42 login page opens in the browser and the tests
# wait for you to log in (AUTH_TIMEOUT seconds, 180 by default).
# test_password.sh (email + password accounts) needs no one, and hands its
# own session over when the 42 login did not happen. That session is used by
# test_pages.sh, then logged out by test_logout.sh: the order matters.
# BASE_URL=https://host:port overrides the target.
AUTH_TESTS = backend/tests/test_auth
test_auth:
	@jar=$$(mktemp); \
	status=0; \
	for t in test_login test_password test_pages test_logout; do \
		t=$(AUTH_TESTS)/$$t.sh; \
		AUTH_JAR=$$jar COMPOSE="$(COMPOSE)" sh $$t || status=1; \
		echo; \
	done; \
	rm -f $$jar; \
	exit $$status


# Regenerate the Alembic migration(s) from scratch: wipes migrations/versions/
# and re-diffs an empty throwaway Postgres against the current models. Only
# produces the CREATE TABLE/INDEX/FK statements - extensions, triggers and
# lookup-table seed data still need to be added by hand afterwards. Run
# `make test` once that's done to validate it applies cleanly end-to-end.
migrate-fresh:
	@rm -f backend/migrations/versions/*.py
	@docker rm -f lb42_migrate_db >/dev/null 2>&1 || true
	@docker run -d --rm --name lb42_migrate_db \
		-e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=lebon42_migrate \
		-p 127.0.0.1:5434:5432 \
		docker.io/library/postgres:18-alpine >/dev/null
	@until docker exec lb42_migrate_db pg_isready -U postgres >/dev/null 2>&1; do sleep 0.5; done
	cd backend \
	&& export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5434 POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres POSTGRES_DB=lebon42_migrate \
	&& uv run alembic revision --autogenerate -m "initial schema"; \
	status=$$?; \
	docker stop lb42_migrate_db >/dev/null; \
	exit $$status

# Re-seed demo data into the running dev api container (idempotent - skips
# if listings already exist). Not needed after a fresh `make dev` since
# SEED_DEMO_DATA=true already runs it on startup; useful to re-run on demand.
# docker compose exec -e KEY=VAL service cmd is supported by both docker-compose and podman-compose, otherwise docker-c uses `-` and podman `_`
seed_dev: $(SECRET_FILES)
	$(COMPOSE_DEV) exec \
		-e POSTGRES_USER=$$(cat secrets/POSTGRES_USER) \
		-e POSTGRES_PASSWORD=$$(cat secrets/POSTGRES_PASSWORD) \
		api python -m app.seeds

seed_prod: $(SECRET_FILES)
	$(COMPOSE) exec \
		-e POSTGRES_USER=$$(cat secrets/POSTGRES_USER) \
		-e POSTGRES_PASSWORD=$$(cat secrets/POSTGRES_PASSWORD) \
		api python -m app.seeds

.PHONY: all up dev down clean fclean re prune ps logs test test_auth migrate-fresh seed
