#!/bin/sh
# GET /api/auth/login and GET /api/auth/callback, driven with curl, ending
# with a real 42 login: the intra page opens in the browser and you log in.
#
# AUTH_JAR: cookie jar the real session is written to, for test_logout.sh.
# COMPOSE:  compose command, to read the proxy logs (see real_login below).
# AUTH_TIMEOUT: seconds to wait for the intra login (default 180).

# Load helpers and env variables
. "$(dirname "$0")/lib.sh"

AUTH_JAR=${AUTH_JAR:-$TMP/jar}
AUTH_TIMEOUT=${AUTH_TIMEOUT:-180}

echo "== login"
require_stack

# --- /auth/login -----------------------------------------------------------

request GET "$API/auth/login"
if [ "$STATUS" = 503 ]; then
	# FT_CLIENT_ID / FT_CLIENT_SECRET empty: the route refuses rather than
	# sending the user to an intra error page.
	assert_status "login without 42 credentials is refused" 503
	skip "login redirect and real login" "secrets/FT_CLIENT_ID or FT_CLIENT_SECRET is empty"
	summary
	exit
fi

assert_status "login redirects" 307
location=$(header location)
assert_contains "redirects to the intra authorize page" "$location" "https://api.intra.42.fr/oauth/authorize?"
assert_contains "asks for an authorization code" "$location" "response_type=code"
assert_contains "sends the client_id" "$location" "client_id="
assert_contains "sends the callback as redirect_uri" "$location" "redirect_uri=https%3A%2F%2F"
assert_not_contains "never leaks the client secret" "$location" "client_secret"

state_cookie=$(set_cookie oauth_state)
state=$(cookie_value oauth_state)
if [ -n "$state" ]; then pass "sets the oauth_state cookie"
else fail "sets the oauth_state cookie" "no Set-Cookie: oauth_state"; fi
assert_contains "state in the URL matches the cookie" "$location" "state=$state"
assert_contains "state cookie is HttpOnly" "$state_cookie" "HttpOnly"
assert_contains "state cookie is Secure" "$state_cookie" "Secure"
assert_contains "state cookie is SameSite=lax" "$state_cookie" "SameSite=lax"
assert_contains "state cookie is scoped to /api/auth/" "$state_cookie" "Path=/api/auth/"
assert_contains "state cookie expires" "$state_cookie" "Max-Age="
assert_not_contains "login does not open a session" "$(set_cookie session)" "session="

request GET "$API/auth/login"
if [ "$(cookie_value oauth_state)" != "$state" ]; then pass "each login gets a fresh state"
else fail "each login gets a fresh state" "same state twice: $state"; fi

# POST /auth/login is the email + password login (test_password.sh): without
# credentials it is refused, and it never starts a 42 login
request POST "$API/auth/login"
assert_status "POST /auth/login without credentials is refused" 422
assert_eq "and starts no 42 login" "$(cookie_value oauth_state)" ""

# --- next: where the callback lands after a successful login ---------------

request GET "$API/auth/login" -G --data-urlencode "next=/messages?tab=2"
next_cookie=$(set_cookie oauth_next)
assert_contains "valid next is kept for the callback" "$next_cookie" "oauth_next=%2Fmessages%3Ftab%3D2"
assert_contains "next cookie is scoped to /api/auth/" "$next_cookie" "Path=/api/auth/"
assert_contains "next cookie is HttpOnly" "$next_cookie" "HttpOnly"

# Each one would send the browser to another host, or is not a page.
tab=$(printf '\t')
for bad in "//evil.com" "https://evil.com" "evil.com" "/\\evil.com" "/$tab/evil.com" "/api/auth/login"; do
	request GET "$API/auth/login" -G --data-urlencode "next=$bad"
	assert_status "next=$bad: login still works" 307
	assert_contains "next=$bad: ignored" "$(set_cookie oauth_next)" "Max-Age=0"
done

# A failed login ignores next: the page asked for would bounce back to the login.
request GET "$API/auth/callback" -G --data-urlencode "error=access_denied" \
	-b "oauth_state=$state; oauth_next=%2Fmessages"
assert_contains "failed login lands on the app root, not next" "$(header location)" "/?auth_error=denied"
assert_contains "next cookie is cleared" "$(set_cookie oauth_next)" "Max-Age=0"

# --- /auth/callback, failures ----------------------------------------------
# Every outcome is a 303 back to the app: success lands on it plain, failure
# with ?auth_error=<code>. Never a session cookie in the failure cases.

callback_fails_with() {
	desc=$1 code=$2
	shift 2
	request GET "$API/auth/callback" "$@"
	assert_status "$desc: redirects to the app" 303
	assert_contains "$desc: auth_error=$code" "$(header location)" "auth_error=$code"
	assert_eq "$desc: no session" "$(cookie_value session)" ""
	assert_contains "$desc: state cookie is cleared" "$(set_cookie oauth_state)" "Max-Age=0"
}

callback_fails_with "user declined on the intra" denied \
	-G --data-urlencode "error=access_denied" -b "oauth_state=$state"

callback_fails_with "no state cookie" invalid_state \
	-G --data-urlencode "code=abc" --data-urlencode "state=$state"

callback_fails_with "no state parameter" invalid_state \
	-G --data-urlencode "code=abc" -b "oauth_state=$state"

callback_fails_with "state does not match the cookie" invalid_state \
	-G --data-urlencode "code=abc" --data-urlencode "state=forged" -b "oauth_state=$state"

# compare_digest on str raises on non-ASCII: must stay a clean rejection, not a 500
callback_fails_with "non-ASCII state" invalid_state \
	-G --data-urlencode "code=abc" --data-urlencode "state=été" -b "oauth_state=$state"

callback_fails_with "state ok but no code" invalid_code \
	-G --data-urlencode "state=$state" -b "oauth_state=$state"

# The API really calls the intra here, which refuses a made-up code.
callback_fails_with "code unknown to the intra" invalid_code \
	-G --data-urlencode "code=not-a-real-code" --data-urlencode "state=$state" -b "oauth_state=$state"

# --- real login ------------------------------------------------------------
# The intra sends the browser, not curl, back to /api/auth/callback. curl holds
# the state cookie, so the browser's callback is refused as invalid_state
# before the API touches the code, which stays unused. nginx logs that request
# line: we pick our code out of it and replay the callback with curl, which
# does the real code exchange with the intra and receives the session.

real_login() {
	if [ -z "$COMPOSE" ]; then
		skip "real 42 login" "COMPOSE not set, cannot read the proxy logs: run it with make test_auth"
		return
	fi

	: > "$AUTH_JAR"
	request GET "$API/auth/login" -G --data-urlencode "next=/messages" -c "$AUTH_JAR"
	authorize_url=$(header location)
	state=$(cookie_value oauth_state)

	printf '\n  Log in on the 42 page opened in your browser (%ss max).\n' "$AUTH_TIMEOUT"
	printf '  The app will then show auth_error=invalid_state: expected, curl finishes the login.\n'
	printf '  If no page opened: %s\n\n' "$authorize_url"
	xdg-open "$authorize_url" >/dev/null 2>&1 || open "$authorize_url" >/dev/null 2>&1 || true

	query=
	waited=0
	while [ "$waited" -lt "$AUTH_TIMEOUT" ]; do
		query=$($COMPOSE logs --no-color proxy 2>/dev/null \
			| sed -n 's|.*"GET /api/auth/callback?\([^ ]*\) HTTP.*|\1|p' \
			| grep -F "state=$state" | tail -n 1)
		[ -n "$query" ] && break
		sleep 2
		waited=$((waited + 2))
	done
	if [ -z "$query" ]; then
		fail "real 42 login" "no callback for our state after ${AUTH_TIMEOUT}s"
		return
	fi
	pass "the intra sent the browser back to the callback"

	code=$(printf '%s' "$query" | tr '&' '\n' | sed -n 's/^code=//p')
	if [ -z "$code" ]; then
		fail "real 42 login" "the intra sent no code: $query"
		return
	fi

	request GET "$API/auth/callback?$query" -b "$AUTH_JAR" -c "$AUTH_JAR"
	assert_status "real login: redirects to the app" 303
	assert_eq "real login: lands on the page asked for" "$(header location)" "/messages"
	session_cookie=$(set_cookie session)
	if [ -n "$(cookie_value session)" ]; then pass "real login: opens a session"
	else fail "real login: opens a session" "no Set-Cookie: session"; fi
	assert_contains "session cookie is HttpOnly" "$session_cookie" "HttpOnly"
	assert_contains "session cookie is Secure" "$session_cookie" "Secure"
	assert_contains "session cookie is SameSite=lax" "$session_cookie" "SameSite=lax"
	assert_contains "session cookie is sent to the whole site" "$session_cookie" "Path=/"
	assert_contains "session cookie expires" "$session_cookie" "Max-Age="
	assert_contains "state cookie is cleared" "$(set_cookie oauth_state)" "Max-Age=0"

	request GET "$API/v1/auth/me" -b "$AUTH_JAR"
	assert_status "me with the new session is 200" 200
	assert_contains "me returns the user" "$(cat "$TMP/body")" "public_id"

	# The intra codes are single use: a replayed callback URL cannot log in again.
	request GET "$API/auth/callback" -G --data-urlencode "code=$code" \
		--data-urlencode "state=$state" -b "oauth_state=$state"
	assert_contains "replayed code: auth_error=invalid_code" "$(header location)" "auth_error=invalid_code"
	assert_eq "replayed code: no session" "$(cookie_value session)" ""
}

real_login

summary
