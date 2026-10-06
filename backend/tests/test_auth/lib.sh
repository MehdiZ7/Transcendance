# Shared helpers for the curl auth tests. Sourced, not run.
#
# Targets the running stack through nginx (make up / make dev), so what is
# tested is what a browser gets: cookies, redirects and headers included.

BASE_URL=${BASE_URL:-https://localhost:8443}
API="$BASE_URL/api"

PASS=0
FAIL=0
SKIP=0

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# -k: the dev certificate is self-signed.
# No -L: the redirects are what we assert on.
CURL="curl -sk --max-time 10"

# request METHOD URL [curl args...]
# Leaves the status in $STATUS, the headers in $TMP/headers, the body in $TMP/body.
# A 429 from nginx's per-IP zones is retried: the scripts send bursts (about
# 20 /api/auth/ requests in a second) that use up auth_per_ip, and what is
# under test is the API behind it. nginx's 429 always says Retry-After: 1;
# the API's own (per-email password limit) waits longer and is returned.
request() {
	method=$1 url=$2
	shift 2
	tries=0
	while :; do
		STATUS=$($CURL -X "$method" -D "$TMP/headers" -o "$TMP/body" -w '%{http_code}' "$@" "$url") \
			|| STATUS=000
		if [ "$STATUS" != 429 ] || [ "$(header retry-after)" != 1 ] || [ "$tries" -ge 30 ]; then
			return 0
		fi
		tries=$((tries + 1))
		sleep 2
	done
}

# header NAME: value of the first NAME header of the last response, CR stripped
header() {
	grep -i "^$1:" "$TMP/headers" | head -n 1 | cut -d: -f2- | sed 's/^ //' | tr -d '\r'
}

# set_cookie NAME: the full Set-Cookie line for cookie NAME in the last response
set_cookie() {
	grep -i "^set-cookie: $1=" "$TMP/headers" | head -n 1 | cut -d: -f2- | sed 's/^ //' | tr -d '\r'
}

# cookie_value NAME: value of cookie NAME set by the last response
cookie_value() {
	set_cookie "$1" | cut -d';' -f1 | cut -d= -f2-
}

pass() { PASS=$((PASS + 1)); printf '  \033[32mok\033[0m    %s\n' "$1"; }
fail() { FAIL=$((FAIL + 1)); printf '  \033[31mFAIL\033[0m  %s\n        %s\n' "$1" "$2"; }
skip() { SKIP=$((SKIP + 1)); printf '  \033[33mskip\033[0m  %s (%s)\n' "$1" "$2"; }

assert_status() {
	if [ "$STATUS" = "$2" ]; then pass "$1"; else fail "$1" "expected HTTP $2, got $STATUS"; fi
}

# assert_contains DESC HAYSTACK NEEDLE (case-insensitive)
assert_contains() {
	if printf '%s' "$2" | grep -qiF -- "$3"; then pass "$1"
	else fail "$1" "'$3' not found in: $2"; fi
}

assert_not_contains() {
	if printf '%s' "$2" | grep -qiF -- "$3"; then fail "$1" "'$3' unexpectedly found in: $2"
	else pass "$1"; fi
}

assert_eq() {
	if [ "$2" = "$3" ]; then pass "$1"; else fail "$1" "expected '$3', got '$2'"; fi
}

# Aborts the whole file when the stack is not up: every test would fail
# for the same reason and hide it.
require_stack() {
	request GET "$API/v1/health"
	if [ "$STATUS" != 200 ]; then
		echo "stack unreachable at $BASE_URL (GET /api/v1/health -> $STATUS): run make up or make dev" >&2
		exit 2
	fi
}

summary() {
	printf '\n%d passed, %d failed, %d skipped\n' "$PASS" "$FAIL" "$SKIP"
	[ "$FAIL" -eq 0 ]
}
