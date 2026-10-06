#!/bin/sh
# Email + password accounts, driven with curl through nginx:
# POST /api/auth/register, POST /api/auth/login, POST /api/auth/password.
# Not interactive: it creates the accounts it needs, with unique example.com
# addresses (left in the database, like the e2e accounts). Assumes the default
# RATE_PASSWORD_ATTEMPTS_PER_HOUR (10) and REGISTER_BLOCKED_EMAIL_DOMAINS.
#
# AUTH_JAR: if given and holding no session (no 42 login happened), a session
# of an account created here is written to it, so that test_pages.sh and
# test_logout.sh still run their logged-in half.

. "$(dirname "$0")/lib.sh"

echo "== password"
require_stack

RUN=$(date +%s)$$
PASSWORD="correct horse battery"
JSON="Content-Type: application/json"
# a seeded 42 account: it has no password
FT_ONLY="lmilando@student.42.fr"

# post_json URL JSON [curl args...]
post_json() {
	url=$1 body=$2
	shift 2
	request POST "$url" -H "$JSON" --data-raw "$body" "$@"
}

# register EMAIL [curl args...] / login EMAIL PASSWORD [curl args...]
register() {
	email_=$1
	shift
	post_json "$API/auth/register" \
		"{\"email\":\"$email_\",\"password\":\"$PASSWORD\",\"display_name\":\"Curl $RUN\"}" "$@"
}
login() {
	email_=$1 password_=$2
	shift 2
	post_json "$API/auth/login" "{\"email\":\"$email_\",\"password\":\"$password_\"}" "$@"
}

# field NAME: a top-level string, number or boolean of the last JSON body
field() {
	sed -n "s/.*\"$1\":\"\{0,1\}\([^,\"}]*\)\"\{0,1\}[,}].*/\1/p" "$TMP/body"
}

# login_time EMAIL PASSWORD: "STATUS SECONDS" of one login, nginx's 429s retried
login_time() {
	while :; do
		out=$($CURL -D "$TMP/theaders" -o /dev/null -w '%{http_code} %{time_total}' -H "$JSON" \
			--data-raw "{\"email\":\"$1\",\"password\":\"$2\"}" "$API/auth/login")
		[ "${out% *}" = 429 ] && tr -d '\r' < "$TMP/theaders" | grep -qi '^retry-after: 1$' || break
		sleep 2
	done
	echo "$out"
}

# refusal_time EMAIL: median seconds of 3 refused logins, empty if one of them
# was not a 401 (the per-email limit, reached by earlier runs within the hour)
refusal_time() {
	times=""
	for n in 1 2 3; do
		out=$(login_time "$1" "wrong $n")
		[ "${out% *}" = 401 ] || return 0
		times="$times${out#* }
"
	done
	printf '%s' "$times" | sort -n | sed -n 2p
}

# is_limited: the last response is the API's per-email 429, not a result
is_limited() { [ "$STATUS" = 429 ]; }

# --- register --------------------------------------------------------------

email="curl-$RUN@example.com"
jar="$TMP/jar"

register "$email" -c "$jar"
assert_status "register creates the account" 201
cookie=$(set_cookie session)
assert_contains "and opens a session" "$cookie" "session="
assert_contains "session cookie is HttpOnly" "$cookie" "HttpOnly"
assert_contains "session cookie is Secure" "$cookie" "Secure"
assert_contains "session cookie is SameSite=Lax" "$cookie" "SameSite=lax"
assert_eq "answers has_password" "$(field has_password)" "true"
assert_not_contains "never returns the hash" "$(cat "$TMP/body")" "password_hash"
assert_not_contains "never echoes the password" "$(cat "$TMP/body")" "$PASSWORD"

request GET "$API/v1/auth/me" -b "$jar"
assert_status "the session works on /api/v1" 200
assert_eq "/auth/me is the new account" "$(field email)" "$email"
request GET "$API/v1/users/me" -b "$jar"
assert_eq "/users/me says has_password" "$(field has_password)" "true"

register "$(printf '%s' "$email" | tr '[:lower:]' '[:upper:]')"
assert_status "the same email in capitals is taken" 409
assert_eq "and opens no session" "$(set_cookie session)" ""

register "$FT_ONLY"
assert_status "a 42 student's address is refused" 403

register "curl-$RUN@student.42.fr"
assert_status "any student.42.fr address is refused" 403

long=$(printf '%0129d' 0)
post_json "$API/auth/register" "{\"email\":\"not-an-email\",\"password\":\"$PASSWORD\",\"display_name\":\"X\"}"
assert_status "a malformed email is refused" 422
post_json "$API/auth/register" "{\"email\":\"v1-$RUN@example.com\",\"password\":\"7 chars\",\"display_name\":\"X\"}"
assert_status "a password under 8 characters is refused" 422
post_json "$API/auth/register" "{\"email\":\"v2-$RUN@example.com\",\"password\":\"$long\",\"display_name\":\"X\"}"
assert_status "a password over 128 characters is refused" 422
post_json "$API/auth/register" "{\"email\":\"v3-$RUN@example.com\",\"password\":\"$PASSWORD\",\"display_name\":\"   \"}"
assert_status "a blank display name is refused" 422

request POST "$API/auth/register" -H "Content-Type: text/plain" \
	--data-raw "{\"email\":\"v4-$RUN@example.com\",\"password\":\"$PASSWORD\",\"display_name\":\"X\"}"
assert_status "a text/plain body is refused: no cross-site form can post it" 422

big=$(head -c 70000 /dev/zero | tr '\0' a)
post_json "$API/auth/register" "{\"email\":\"$big\"}"
assert_status "a body over 64 KB is refused by nginx" 413

request GET "$API/auth/register"
assert_status "GET /auth/register is not allowed" 405

# --- login -----------------------------------------------------------------

login "$email" "$PASSWORD" -c "$TMP/jar2"
assert_status "login with the right password" 200
assert_contains "opens a session" "$(set_cookie session)" "session="
assert_eq "answers the account" "$(field email)" "$email"

login "$(printf '%s' "$email" | tr '[:lower:]' '[:upper:]')" "$PASSWORD"
assert_status "login ignores the email's case" 200

login "$email" "wrong password"
assert_status "a wrong password is refused" 401
wrong_body=$(cat "$TMP/body")
assert_eq "and opens no session" "$(set_cookie session)" ""
login "nobody-$RUN@example.com" "$PASSWORD"
assert_status "an unknown email is refused" 401
assert_eq "with the same answer as a wrong password" "$(cat "$TMP/body")" "$wrong_body"
# $FT_ONLY is the same account on every run: its per-email budget (10 an
# hour, 4 per run) can run out when the script is run again and again.
login "$FT_ONLY" "$PASSWORD"
if is_limited; then
	skip "a 42 account without a password is refused" "its per-email limit is reached, rerun in an hour"
else
	assert_status "a 42 account without a password is refused" 401
	assert_eq "with the same answer again" "$(cat "$TMP/body")" "$wrong_body"
fi

# Same work in every case (a dummy hash when there is no real one): an unknown
# email or a 42 account must not answer much faster than a wrong password.
# Without the dummy hash they answer in about 1 ms against tens of ms.
w=$(refusal_time "$email")
u=$(refusal_time "ghost-$RUN@example.com")
f=$(refusal_time "$FT_ONLY")
if [ -z "$w" ] || [ -z "$u" ] || [ -z "$f" ]; then
	skip "refusals take as long" "a login was not a 401: per-email limit reached by earlier runs"
else
	desc="refusals take as long (wrong password ${w}s, unknown ${u}s, 42 account ${f}s)"
	if awk "BEGIN { exit !($u >= 0.5 * $w && $f >= 0.5 * $w) }"; then pass "$desc"
	else fail "$desc" "an unknown email or a 42 account answers much faster"; fi
fi

# --- per-email limit -------------------------------------------------------

target="limit-$RUN@example.com"
i=0
while [ "$i" -lt 10 ]; do
	login "$target" "guess $i"
	[ "$STATUS" = 401 ] || break
	i=$((i + 1))
done
assert_eq "10 guesses on one email are answered" "$i" 10
login "$target" "guess 10"
assert_status "the 11th guess on that email is refused" 429
wait_s=$(header retry-after)
if [ "${wait_s:-0}" -gt 60 ]; then pass "by the API, for a while (Retry-After: ${wait_s}s)"
else fail "by the API, for a while" "Retry-After: '$wait_s' (nginx's is 1)"; fi
login "other-$RUN@example.com" "guess"
assert_status "another email is not affected" 401

# --- change password -------------------------------------------------------

changer="curl-change-$RUN@example.com"
cjar="$TMP/cjar"
register "$changer" -c "$cjar"

post_json "$API/auth/password" "{\"new_password\":\"brand new secret\",\"current_password\":\"$PASSWORD\"}"
assert_status "changing a password needs a session" 401
post_json "$API/auth/password" "{\"new_password\":\"brand new secret\",\"current_password\":\"wrong\"}" -b "$cjar"
assert_status "a wrong current password is refused" 400
post_json "$API/auth/password" "{\"new_password\":\"brand new secret\"}" -b "$cjar"
assert_status "a missing current password is refused" 400
post_json "$API/auth/password" "{\"new_password\":\"short\",\"current_password\":\"$PASSWORD\"}" -b "$cjar"
assert_status "a new password under 8 characters is refused" 422
post_json "$API/auth/password" "{\"new_password\":\"brand new secret\",\"current_password\":\"$PASSWORD\"}" -b "$cjar"
assert_status "the right current password changes it" 204

login "$changer" "$PASSWORD"
assert_status "the old password no longer works" 401
login "$changer" "brand new secret"
assert_status "the new one does" 200

# --- logout ----------------------------------------------------------------

request POST "$API/auth/logout" -b "$jar" -c "$jar"
assert_status "logout" 204
request GET "$API/v1/auth/me" -b "$jar"
assert_status "the jar holds no session afterwards" 401

# --- hand a session to the next scripts ------------------------------------

if [ -n "$AUTH_JAR" ] && ! grep -q "	session	" "$AUTH_JAR" 2>/dev/null; then
	login "$email" "$PASSWORD" -c "$AUTH_JAR"
	assert_status "session for test_pages.sh and test_logout.sh" 200
fi

summary
