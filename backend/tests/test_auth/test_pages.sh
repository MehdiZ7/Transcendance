#!/bin/sh
# Pages that need a session, refused by front/src/proxy.ts before they render.
# The proxy asks the backend (GET /api/v1/auth/me) whether the session is
# valid and which role it carries.
#
# AUTH_JAR: cookie jar holding the real session test_login.sh opened.
# Without a session in it, the logged-in tests are skipped.

. "$(dirname "$0")/lib.sh"

echo "== pages"
require_stack

PAGES="/profile /messages /listings/create /moderation /analytics"

# --- anonymous -------------------------------------------------------------

# assert_to_login DESC PATH: last response sends the browser to the login page
# (email or 42), with PATH as next so it comes back to it
assert_to_login() {
	assert_status "$1: redirected" 307
	next=$(printf '%s' "$2" | sed 's|/|%2F|g; s|?|%3F|g; s|=|%3D|g')
	assert_eq "$1: to the login page, back here after" "$(header location)" "/login?next=$next"
}

for page in $PAGES; do
	request GET "$BASE_URL$page"
	assert_to_login "$page without a session" "$page"
done

request GET "$BASE_URL/profile/00000000-0000-0000-0000-000000000000?tab=2"
assert_to_login "another profile, query kept" "/profile/00000000-0000-0000-0000-000000000000?tab=2"

request GET "$BASE_URL/messages" -b "session=not.a.jwt"
assert_to_login "/messages with a garbage session" "/messages"

request GET "$BASE_URL/"
assert_status "home is public" 200

request GET "$BASE_URL/login?next=%2Fmessages"
assert_status "the login page is public" 200

# the first public_id is the listing's; the seller's comes after it
listing=$($CURL "$API/v1/listings?limit=1" | grep -o '"public_id":"[^"]*"' | head -n 1 | cut -d'"' -f4)
if [ -n "$listing" ]; then
	request GET "$BASE_URL/listings/$listing"
	assert_status "a listing is public" 200
else
	skip "a listing is public" "no listing in the db"
fi

# A hover prefetch is not checked by the proxy, so not redirected either
request GET "$BASE_URL/messages" -H "next-router-prefetch: 1"
assert_not_contains "prefetch is not sent to the login" "$(header location)" "/login"

# --- logged in -------------------------------------------------------------

if [ -z "$AUTH_JAR" ] || ! grep -q "	session	" "$AUTH_JAR" 2>/dev/null; then
	skip "pages with a real session" "no session from test_login.sh"
	summary
	exit
fi

request GET "$API/v1/auth/me" -b "$AUTH_JAR"
role=$(sed -n 's/.*"role":"\([a-z]*\)".*/\1/p' "$TMP/body")

for page in /profile /messages /listings/create; do
	request GET "$BASE_URL$page" -b "$AUTH_JAR"
	assert_status "$page with a session" 200
done

# assert_role_page PAGE ALLOWED_ROLES...: 200 for those roles, else back to /
assert_role_page() {
	page=$1
	shift
	request GET "$BASE_URL$page" -b "$AUTH_JAR"
	case " $* " in
		*" $role "*) assert_status "$page as $role" 200 ;;
		*)
			assert_status "$page as $role: redirected" 307
			assert_eq "$page as $role: to the home page" "$(header location)" "/"
			;;
	esac
}
assert_role_page /moderation moderator admin
assert_role_page /analytics admin

summary
