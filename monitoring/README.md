# monitoring — Metrics, alerts and dashboards

The observability stack of **Le Bon 42**:

- **Prometheus** collects metrics from the API and from PostgreSQL every 15
  seconds, keeps them for 15 days, and evaluates the alert rules;
- **postgres-exporter** turns PostgreSQL's internal statistics into metrics
  Prometheus can read;
- **Grafana** displays them in a ready-made dashboard, *FastAPI Overview*.

This folder holds their configuration. The services themselves are defined in
[`../docker-compose.yml`](../docker-compose.yml) and start with the rest of the
stack.

| Related topic | Document |
|---|---|
| Project overview | [`../README.md`](../README.md) |
| The API's `/metrics` endpoint and logs | [`../backend/README.md`](../backend/README.md#observability) |
| The `/grafana/` route and its headers | [`../nginx/README.md`](../nginx/README.md) |

> [!NOTE]
> This stack monitors the **technical health** of the service: traffic,
> errors, latency, resources. Business figures (listings, sales, reports) are
> in the admin analytics dashboard of the app, served by `/api/v1/analytics`.

## Contents

- [Quick start](#quick-start)
- [At a glance](#at-a-glance)
- [Files](#files)
- [How the pieces fit](#how-the-pieces-fit)
- [Metrics collected](#metrics-collected)
- [Grafana](#grafana)
- [Prometheus](#prometheus)
- [Alerts](#alerts)
- [Data and volumes](#data-and-volumes)
- [Security](#security)
- [Production checklist](#production-checklist)
- [Troubleshooting](#troubleshooting)
- [Known issues](#known-issues)

---

## Quick start

1. **Start the stack** from the repository root with `make dev` or `make up`.
   The monitoring services start with it.
2. **Open Grafana** at <https://localhost:8443/grafana/> and sign in with
   the contents of `secrets/GRAFANA_USER` (`lb42`) and
   `secrets/GRAFANA_PASSWORD` (generated on the first `make`):
   `cat secrets/GRAFANA_PASSWORD`.
3. **Open the dashboard.** Grafana's home page is the *FastAPI Overview*
   dashboard. It is also under *Dashboards* → *Transcendence*, and at
   <https://localhost:8443/grafana/d/fastapi-overview/fastapi-overview>.
4. **Check the collection:** in Grafana, open *Explore* and run the query
   `up`. Both targets, `fastapi-backend` and `postgres`, should show `1`.
5. **Generate some traffic** by browsing the site. The graphs use one-minute
   rates, so they fill within about 30 seconds.

---

## At a glance

| Component | Image | Role | Reach it at | Data volume |
|---|---|---|---|---|
| Prometheus | `prom/prometheus:v2.54.1` | Scrapes every 15 s, evaluates alert rules every 15 s, stores 15 days | Internal only: `prometheus:9090`, queried by Grafana | `promdata` |
| Grafana | `grafana/grafana:11.2.0` | Dashboards | <https://localhost:8443/grafana/> | `grafanadata` |
| postgres-exporter | `prometheuscommunity/postgres-exporter:v0.17.1` | Exposes PostgreSQL statistics as metrics | Internal only: `postgres-exporter:9187` | — |
| API metrics | `prometheus-fastapi-instrumentator` 8.1, in the API | Exposes HTTP and process metrics | Internal only: `api:8000/metrics` | — |

All three services restart automatically (`restart: unless-stopped`).
Prometheus and Grafana also run with `no-new-privileges`.

---

## Files

```
monitoring/
├── prometheus/
│   ├── prometheus.yml              scrape targets, intervals, rule file
│   └── alert.rules.yml             alert rules
└── grafana/
    ├── provisioning/
    │   ├── datasources/datasource.yml   the Prometheus data source
    │   └── dashboards/dashboards.yml    where Grafana loads dashboards from
    └── dashboards/
        └── fastapi_overview.json        the FastAPI Overview dashboard
```

Every file is mounted **read-only** into its container, straight from the
repository:

| Repository path | Mounted at |
|---|---|
| `prometheus/prometheus.yml` | `prometheus:/etc/prometheus/prometheus.yml` |
| `prometheus/alert.rules.yml` | `prometheus:/etc/prometheus/alert.rules.yml` |
| `grafana/provisioning/` | `grafana:/etc/grafana/provisioning` |
| `grafana/dashboards/` | `grafana:/var/lib/grafana/dashboards` |

Nothing is copied into an image, so no rebuild is ever needed. How each
change is applied is explained in [Grafana](#editing-the-dashboard) and
[Prometheus](#applying-a-configuration-change).

---

## How the pieces fit

```
                     scrape every 15 s
   api:8000/metrics  ◀───────────────┐
                                     │
   postgres-exporter:9187 ◀──────────┼──── prometheus:9090 ──▶ alert rules (no notifications)
          │                          │           ▲
          └──▶ db:5432 (SQL)                     │ PromQL queries
                                                 │
   browser ──HTTPS──▶ nginx /grafana/ ──▶ grafana:3000
```

- **Networks.** Prometheus, postgres-exporter and the database are on the
  `backend` network only. Grafana is on `backend` (to query Prometheus) and
  `front` (so nginx can reach it).
- **Prometheus is internal.** It publishes no host port and nginx does not
  route it, because it has no authentication: anyone reaching it could read
  every metric and run arbitrary queries. Grafana, behind its sign-in, is its
  only client. See [Accessing Prometheus](#accessing-prometheus).
- **Pull model.** Prometheus fetches the metrics; the API and the exporter
  only answer. A target that does not answer is marked `DOWN`, and `up` drops
  to `0`.
- **Start order.** postgres-exporter waits for the database to be healthy.
  Grafana starts after Prometheus.

---

## Metrics collected

### From the API (job `fastapi-backend`)

The API exposes `/metrics` through
[`prometheus-fastapi-instrumentator`](https://github.com/trallnag/prometheus-fastapi-instrumentator),
configured in [`backend/src/app/main.py`](../backend/src/app/main.py).

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `http_requests_total` | Counter | `handler`, `method`, `status` | Requests served |
| `http_request_duration_seconds` | Histogram | `handler`, `method` | Response time. **Only 3 buckets**: 0.1, 0.5 and 1 s |
| `http_request_duration_highr_seconds` | Histogram | none | Response time with 21 buckets, from 10 ms to 60 s. Use it for accurate percentiles |
| `http_request_size_bytes`, `http_response_size_bytes` | Summary | `handler` | Body sizes |
| `process_cpu_seconds_total`, `process_resident_memory_bytes`, `process_open_fds`… | Counter, gauges | none | Resources of the API process |
| `python_gc_*`, `python_info` | Various | — | Python runtime |

- **`handler`** is the route **template**, such as
  `/api/v1/listings/{public_id}`, so the number of series stays small. Paths
  that match no route are not recorded.
- **`status`** is the exact code (`200`, `404`…), not a group like `2xx`.
- **Excluded:** `/metrics`, `/api/v1/health` and the admin SSE stream
  `/api/v1/analytics/stream`. WebSocket traffic (`/api/ws`) is not counted
  either.
- **Restarts** reset the counters. `rate()` and `increase()` handle that
  correctly.
- **Extra labels** added by Prometheus: `job`, `instance`,
  `application="lb42-transcendence"`, and `environment="production"`, which is
  hard-coded and also set in development.

### From PostgreSQL (job `postgres`)

postgres-exporter connects to `db:5432` with the application's database
credentials and exposes, among others:

| Metric | Meaning |
|---|---|
| `pg_up` | `1` when the exporter can connect to PostgreSQL, `0` otherwise |
| `pg_database_size_bytes` | Size of each database |
| `pg_stat_database_numbackends` | Open connections per database |
| `pg_stat_database_xact_commit`, `pg_stat_database_xact_rollback` | Committed and rolled-back transactions |
| `pg_stat_database_blks_hit`, `pg_stat_database_blks_read` | Reads served from cache vs from disk |
| `pg_stat_database_deadlocks` | Deadlocks detected |
| `pg_locks_count` | Locks held, by mode |

No dashboard panel uses these yet: explore them in Prometheus, or
[add panels](#editing-the-dashboard). `pg_up` drives the `PostgresDown` alert.

### Not collected

- nginx, the Next.js front and Prometheus itself are not scraped. Grafana's
  own metrics are turned off (see [Accessing Grafana](#accessing-grafana)).
- There is no host or container resource monitoring (such as node-exporter or
  cAdvisor): the only resource metrics are the API process's own.

---

## Grafana

### Accessing Grafana

<https://localhost:8443/grafana/>, through nginx over HTTPS.

**Sign-in.** The admin account comes from the `secrets/GRAFANA_USER` and
`secrets/GRAFANA_PASSWORD` files, mounted as Docker secrets (`lb42` and a
random password generated by `make` on the first run). Sign-up and
anonymous access are disabled.

**Hardening.** On top of the sign-in:

- nginx limits `/grafana/login` with the app's `auth_per_ip` zone (see the
  [nginx README](../nginx/README.md#rate-limiting)), before Grafana's own
  brute-force lockout;
- the session cookie is `Secure` (`GF_SECURITY_COOKIE_SECURE`): Grafana is only
  reached over HTTPS;
- Grafana's own `/metrics` is off (`GF_METRICS_ENABLED=false`), and nginx
  answers `404` on `/grafana/metrics` anyway;
- signed-out visitors do not see the version, on `/grafana/api/health` or the
  sign-in page (`GF_AUTH_ANONYMOUS_HIDE_VERSION`);
- Grafana sends no usage reports and checks for no updates (`GF_ANALYTICS_*`);
- its home page is the project's dashboard and its news feed is off
  (`GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH`, `GF_NEWS_NEWS_FEED_ENABLED`):
  Grafana's own home page fetches grafana.com's blog feed, which the CSP
  blocks, leaving an error in the browser console.

> [!IMPORTANT]
> Grafana reads `secrets/GRAFANA_USER` and `secrets/GRAFANA_PASSWORD` only when
> its database is created, on the very first start. Editing the files
> afterwards has no effect. To change the password later:
>
> ```bash
> docker compose exec grafana grafana cli admin reset-admin-password '<new password>'
> ```

**Serving under `/grafana/`.** Compose sets `GF_SERVER_SERVE_FROM_SUB_PATH=true`
and the public root URL, `https://<SERVER_NAME>:<HTTPS_PORT>/grafana/`, so
Grafana answers on that path behind nginx and builds its links from the address
the browser sees.

### Provisioning

Grafana configures itself at start from
[`grafana/provisioning/`](grafana/provisioning/):

- **Data source** ([`datasource.yml`](grafana/provisioning/datasources/datasource.yml)):
  `Prometheus`, at `http://prometheus:9090`, the default data source. It is
  read-only in the UI. Its `timeInterval` of 15 s matches the scrape interval,
  so Grafana never asks for finer data than exists.
- **Dashboards** ([`dashboards.yml`](grafana/provisioning/dashboards/dashboards.yml)):
  every JSON file in `/var/lib/grafana/dashboards` (the repository's
  [`grafana/dashboards/`](grafana/dashboards/)) is loaded into the
  *Transcendence* folder. Grafana rescans the folder every 10 seconds.

### The FastAPI Overview dashboard

[`fastapi_overview.json`](grafana/dashboards/fastapi_overview.json), uid
`fastapi-overview`. It shows the **last 15 minutes**, refreshes **every
5 seconds**, and uses the browser's time zone. Panel titles are in French; the
English meaning is given below.

| Row | Panel | Shows | Thresholds |
|---|---|---|---|
| *Aperçu Global* (overview) | *Débit Total des Requêtes* | Total requests per second | — |
| | *Taux d'Erreurs Serveur (5xx)* | Share of responses that are 5xx | Yellow from 1 %, red from 5 % |
| | *Taux d'Erreurs Client (4xx)* | Share of responses that are 4xx | Yellow from 5 %, orange from 15 % |
| | *Latence Moyenne* | Average response time | Yellow from 200 ms, red from 1 s |
| *Trafic et Distribution* (traffic) | *Débit par Route* | Requests per second, per route | — |
| | *Codes de Statut HTTP* | Requests per second, per status code | — |
| *Latences et Temps de Réponse* (latency) | *Percentiles de Temps de Réponse* | p50, p90, p95 and p99 response times | — |
| | *Latence Moyenne par Route* | Average response time, per route | — |
| *Ressources Système API* (resources) | *Consommation Mémoire Backend* | Resident (RSS) and virtual memory | — |
| | *Consommation CPU Backend* | CPU usage. `100 %` means one full core | — |

**Reading it.**

- Every value is computed over the **last minute**. A burst of traffic
  appears within about 30 seconds and fades a minute later.
- With no traffic, the rates show `0` and the latency panels are empty.
- Some 4xx responses are normal: `401` while signed out, `404`, `422` on
  invalid input, `429` on rate limits.
- The percentile panel is **approximate**: see [Known issues](#known-issues).

### Editing the dashboard

The dashboard is provisioned from a file, so Grafana refuses to save changes
made in the UI over it. The workflow is:

1. edit the dashboard in Grafana until it looks right;
2. click **Save**: Grafana answers *Cannot save provisioned dashboard* and
   offers the JSON; copy it (or use *Export* → *Export as JSON*);
3. replace the content of
   [`fastapi_overview.json`](grafana/dashboards/fastapi_overview.json) with it;
4. Grafana reloads the file within 10 seconds. No restart is needed. Commit
   the file.

Rules for dashboard files:

- **Keep the `uid`.** It is part of the dashboard's URL.
- **Refer to the data source** as
  `{"type": "prometheus", "uid": "Prometheus"}`, like the existing panels.
- **A new dashboard** is a new JSON file in
  [`grafana/dashboards/`](grafana/dashboards/), with a `uid` of its own. It
  appears in the *Transcendence* folder within 10 seconds.

---

## Prometheus

### Accessing Prometheus

Prometheus is **not reachable from outside**: it publishes no host port and
nginx does not route it, because it has no authentication (see
[Security](#security)). Query it through Grafana, or call its API from inside
its own container:

| To see | In Grafana: *Explore*, data source *Prometheus* | From the container (JSON) |
|---|---|---|
| Each target and its state | `up`: `1` is UP, `0` is DOWN | `docker compose exec prometheus wget -qO- http://127.0.0.1:9090/api/v1/targets`, with the last scrape error |
| Alerts pending or firing | `ALERTS` | `docker compose exec prometheus wget -qO- http://127.0.0.1:9090/api/v1/alerts` |
| Each alert rule and its state | — | `docker compose exec prometheus wget -qO- http://127.0.0.1:9090/api/v1/rules` |
| The configuration actually loaded | — | `docker compose exec prometheus wget -qO- http://127.0.0.1:9090/api/v1/status/config` |
| Any PromQL query, as a table or a graph | Type it in the query field | — |

### Configuration

[`prometheus.yml`](prometheus/prometheus.yml):

| Setting | Value |
|---|---|
| Scrape interval | 15 s |
| Rule evaluation interval | 15 s |
| Rule file | `/etc/prometheus/alert.rules.yml` |
| Retention | 15 days (`--storage.tsdb.retention.time`, in `docker-compose.yml`) |
| Storage | `/prometheus`, on the `promdata` volume |

| Job | Target | Path | Extra labels |
|---|---|---|---|
| `fastapi-backend` | `api:8000` | `/metrics` | `application="lb42-transcendence"`, `environment="production"` |
| `postgres` | `postgres-exporter:9187` | `/metrics` | `application="lb42-db"` |

### Applying a configuration change

1. Edit [`prometheus.yml`](prometheus/prometheus.yml) or
   [`alert.rules.yml`](prometheus/alert.rules.yml).
2. Validate the files:

   ```bash
   docker compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
   docker compose exec prometheus promtool check rules  /etc/prometheus/alert.rules.yml
   ```

3. Restart Prometheus. The data is kept.

   ```bash
   docker compose restart prometheus
   ```

The reload endpoint (`/-/reload`) is not enabled, so it answers `403`.

### Useful queries

Paste these into Grafana's *Explore* or into a dashboard panel:

| Question | PromQL |
|---|---|
| Which targets are up? | `up` |
| Requests per second, per route | `sum by (handler) (rate(http_requests_total[5m]))` |
| The five slowest routes, on average | `topk(5, sum by (handler) (rate(http_request_duration_seconds_sum[5m])) / sum by (handler) (rate(http_request_duration_seconds_count[5m])))` |
| Accurate p95 response time | `histogram_quantile(0.95, sum by (le) (rate(http_request_duration_highr_seconds_bucket[5m])))` |
| Responses per status over the last hour | `sum by (status) (increase(http_requests_total[1h]))` |
| Routes answering 5xx | `sum by (handler, status) (rate(http_requests_total{status=~"5.."}[5m])) > 0` |
| Database size | `pg_database_size_bytes{datname="lb42db"}` |
| Alerts firing now | `ALERTS{alertstate="firing"}` |

---

## Alerts

### The rules

[`alert.rules.yml`](prometheus/alert.rules.yml), group `transcendence_alerts`:

| Alert | Severity | Fires when | For |
|---|---|---|---|
| `BackendDown` | critical | Prometheus cannot scrape the API: `up{job="fastapi-backend"} == 0` | 30 s |
| `HighHttpErrorRate` | warning | More than 5 % of the API's responses are 5xx, over the last minute | 1 min |
| `PostgresDown` | critical | postgres-exporter cannot connect to PostgreSQL: `pg_up == 0` | 30 s |

An alert is **inactive** while its condition is false, **pending** while the
condition is true but for less than the *For* delay, and **firing** after
that. Summaries and descriptions are written in French.

### Where alerts go

> [!WARNING]
> **Nobody is notified.** There is no Alertmanager and no Grafana contact
> point: alerts are only visible as the `ALERTS` metric in Grafana's
> *Explore*, or through Prometheus's API (see
> [Accessing Prometheus](#accessing-prometheus)).
> Receiving them by email or chat needs an Alertmanager service and an
> `alerting:` section in `prometheus.yml`, or Grafana alerting with a contact
> point.

### Blind spots

- **`PostgresDown` depends on the exporter.** If postgres-exporter itself is
  down, `pg_up` disappears instead of dropping to `0`, and the alert never
  fires. The rule below covers that case.
- **`HighHttpErrorRate` stays silent without traffic**, since there is no rate
  to compare. That is intended.
- **Nothing watches latency**, the front, or nginx.

### Adding a rule

Append it to the `rules:` list in
[`alert.rules.yml`](prometheus/alert.rules.yml). For example, to cover the
first blind spot:

```yaml
      - alert: PostgresExporterDown
        expr: up{job="postgres"} == 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "postgres-exporter is down: PostgreSQL is no longer monitored"
```

Then [validate and restart](#applying-a-configuration-change), and check that
the rule is loaded with `/api/v1/rules` (see
[Accessing Prometheus](#accessing-prometheus)).

---

## Data and volumes

| Volume | Holds | Survives |
|---|---|---|
| `promdata` | Prometheus's time series, 15 days | `make down`. Deleted by `make clean`, `make fclean` and `make re` |
| `grafanadata` | Grafana's own database: users and passwords, preferences, dashboards created in the UI | Same |

The provisioned configuration (data source, dashboard folder, the FastAPI
Overview dashboard) comes from the repository, so it is restored on every
start, even after the volumes are deleted. A dashboard created **only** in the
Grafana UI lives in `grafanadata` and is lost with it: export it to
[`grafana/dashboards/`](grafana/dashboards/) to keep it.

---

## Security

| Concern | Current state | Recommendation for a public host |
|---|---|---|
| Prometheus | No authentication. No host port and no nginx route: only containers on the `backend` network reach it, and Grafana is its only client | Keep it that way. Never publish it or route it without authentication in front |
| Grafana credentials | `lb42` / generated | Random by default (`secrets/GRAFANA_PASSWORD`); replace the file **before** the first start to choose it |
| Grafana | No host port published; served over HTTPS via nginx at `/grafana/`. `Secure` session cookie, sign-in rate-limited, `/metrics` off, version hidden from signed-out visitors (see [Hardening](#accessing-grafana)) | TLS-encrypted through nginx |
| API metrics | `/metrics` is not routed by nginx: only containers on the `backend` network reach it | — |
| Exporter credentials | Read from the Docker secrets, never written in a file of this folder. It uses the application's database role, which has full rights | Create a read-only role with the `pg_monitor` privilege for the exporter |

---

## Production checklist

- [ ] Keep the generated `secrets/GRAFANA_PASSWORD`, or replace it (and
      `secrets/GRAFANA_USER`) with your own before the first start.
- [ ] Check in Grafana's *Explore* that `up` is `1` for both targets.
- [ ] Decide who must be told when an alert fires, and add a notification
      channel (see [Where alerts go](#where-alerts-go)).
- [ ] Add the `PostgresExporterDown` rule (see [Adding a rule](#adding-a-rule)).
- [ ] Back up `grafanadata` if dashboards were created in the UI.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Target `postgres` is `DOWN`; `postgres-exporter` keeps restarting; its logs say `failed loading data source user file /run/secrets/POSTGRES_USER: … permission denied` | The exporter runs as user `nobody`, and the secret files on the host are not readable by others (mode `600`) | Give the two files the mode `make` creates them with: `chmod 644 secrets/POSTGRES_USER secrets/POSTGRES_PASSWORD`, keep the `secrets/` directory at `700`, then `docker compose restart postgres-exporter` |
| The exporter logs `Error opening config file "postgres_exporter.yml"` | It looks for an optional configuration file that this setup does not use | Nothing: this warning is harmless |
| Target `fastapi-backend` is `DOWN` with `no such host` | The `api` container is not running | Start the stack; check `docker compose logs api` |
| The dashboard shows `0` or *No data* | No traffic in the last minute, or a target is down | Browse the site, then check the targets (see [Accessing Prometheus](#accessing-prometheus)) |
| Grafana rejects the password in `secrets/GRAFANA_PASSWORD` | The file was changed after the first start, when Grafana stored the password it held then | Reset it with `grafana cli admin reset-admin-password`. See [Accessing Grafana](#accessing-grafana) |
| *Cannot save provisioned dashboard* | Expected: the dashboard comes from a file | Copy the JSON into the file. See [Editing the dashboard](#editing-the-dashboard) |
| A dashboard file change does not appear | Grafana rescans every 10 seconds, and ignores a file with invalid JSON | Wait, then reload the page. Check `docker compose logs grafana` for a parsing error |
| A Prometheus configuration change has no effect | Prometheus reads its files at start | `docker compose restart prometheus`. See [Applying a configuration change](#applying-a-configuration-change) |
| The percentile panel always shows about 50, 90, 95 and 99 ms | The panel uses the 3-bucket histogram, which cannot resolve times below 100 ms | Read the average latency instead, or use `http_request_duration_highr_seconds`. See [Known issues](#known-issues) |
| The memory or CPU panel shows two lines with the same name | The queries do not filter by job: postgres-exporter's own process appears too | Add `{job="fastapi-backend"}` to the queries. See [Known issues](#known-issues) |
| Grafana misbehaves through `https://…/grafana/` under `make up` | nginx's production Content-Security-Policy (its `/grafana/` copy) blocks something Grafana loads | Read the `Refused to …` messages in the browser console; see the [nginx README](../nginx/README.md#security-headers) |
| Firefox's console on Grafana's pages shows `Fingerprinting Protection is altering screen.availWidth and screen.availHeight…` and `WEBGL_debug_renderer_info is deprecated in Firefox…`, both from `fp.esm.js` | Grafana bundles the FingerprintJS library (`fp.esm.js`) to build the `x-grafana-device-id` header of its requests. When it reads the screen size and the WebGL renderer, Firefox's fingerprinting protection logs these two warnings | Nothing: the warnings come from Firefox, not from this setup. They break nothing and cannot be turned off from the server |
| An alert is firing but nobody was told | There is no notification channel | See [Where alerts go](#where-alerts-go) |

---

## Known issues

- **No notifications.** Alerts are evaluated but sent nowhere. See
  [Where alerts go](#where-alerts-go).
- **Approximate percentiles.** The *Percentiles de Temps de Réponse* panel
  uses `http_request_duration_seconds`, whose buckets are 0.1, 0.5 and 1 s.
  `histogram_quantile` interpolates inside a bucket, so every request faster
  than 100 ms is placed somewhere between 0 and 100 ms. When nearly all
  requests take less than 100 ms, as is usual here, the panel shows about 50,
  90, 95 and 99 ms whatever the real times. Replacing the metric
  with `http_request_duration_highr_seconds_bucket` (21 buckets, from 10 ms)
  gives meaningful values.
- **Resource panels are not filtered by job.** The memory and CPU queries
  (`process_resident_memory_bytes`, `process_virtual_memory_bytes`,
  `process_cpu_seconds_total`) also match postgres-exporter's process. Add
  `{job="fastapi-backend"}` to each.
- **`environment="production"`** is hard-coded on the API's metrics, including
  in development.
- **`PostgresDown` is blind** when the exporter itself is down. See
  [Blind spots](#blind-spots).
