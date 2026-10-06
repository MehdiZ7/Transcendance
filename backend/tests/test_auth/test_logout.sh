#!/bin/sh
# POST /api/auth/logout, checked through GET /api/v1/auth/me.
#
# AUTH_JAR: cookie jar holding the real session test_login.sh opened.
# Without a session in it, the logged-in tests are skipped.

. "$(dirname "$0")/lib.sh"

echo "== logout"
require_stack

# --- anonymous -------------------------------------------------------------

request POST "$API/auth/logout"
assert_status "logout without a session still answers 204" 204
cleared=$(set_cookie session)
assert_contains "clears the session cookie" "$cleared" "Max-Age=0"
assert_contains "cleared on the path it was set on" "$cleared" "Path=/"
assert_contains "cleared cookie keeps HttpOnly" "$cleared" "HttpOnly"
assert_eq "no body" "$(cat "$TMP/body")" ""

request GET "$API/auth/logout"
assert_status "GET /auth/logout is not allowed (no logout by <img> link)" 405

request GET "$API/v1/auth/me"
assert_status "me without a session is 401" 401

request GET "$API/v1/auth/me" -b "session=not.a.jwt"
assert_status "me with a garbage session is 401" 401

# --- logged in -------------------------------------------------------------

if [ -z "$AUTH_JAR" ] || ! grep -q "	session	" "$AUTH_JAR" 2>/dev/null; then
	skip "logout of a real session" "no session from test_login.sh"
	summary
	exit
fi

# The jar plays the browser: it stores what Set-Cookie says and sends it back.
request GET "$API/v1/auth/me" -b "$AUTH_JAR" -c "$AUTH_JAR"
assert_status "me with the session is 200" 200

request POST "$API/auth/logout" -b "$AUTH_JAR" -c "$AUTH_JAR"
assert_status "logout is 204" 204
if grep -q "	session	" "$AUTH_JAR"; then
	fail "the browser drops the session cookie" "still in the jar"
else
	pass "the browser drops the session cookie"
fi

request GET "$API/v1/auth/me" -b "$AUTH_JAR"
assert_status "me after logout is 401" 401

summary
