import { useState, useEffect } from "react";
import type { UserProfile } from "@/types/user";
import { usersApi } from "@/lib/api/users";
import { logError } from "@/lib/log";

// cache module level shared with all the users of useCurrentUser
type UserCache =
	| { status: "idle" }
	| { status: "loading"; promise: Promise<UserProfile | null> }
	| { status: "ready"; user: UserProfile | null }
	| { status: "error" };

let cache: UserCache = { status: "idle" };

function loadCurrentUser(): Promise<UserProfile | null> {
	// already solved : send the value in cache
	if (cache.status === "ready") return Promise.resolve(cache.user);
	// loading: we send the same provise for everyone
	if (cache.status === "loading") return cache.promise;

	const promise = usersApi
		.getCurrent()
		.then((me) => {
			cache = { status: "ready", user: me };
			return me;
		})
		.catch((err) => {
			// an error (network, 5xx) is not "anonymous" (anonymous is a 204 -> null):
			// do not cache a definitive null, keep it retryable on the next mount
			cache = { status: "error" };
			throw err;
		});
	cache = { status: "loading", promise };
	return promise;
}

export function useCurrentUser() {
	const [user, setUser] = useState<UserProfile | null>(
		cache.status === "ready" ? cache.user : null,
	);
	// anything but "ready" means the effect below starts (or joins) a request:
	// loading until it answers, so a guard does not redirect on a stale error
	const [isLoading, setIsLoading] = useState(cache.status !== "ready");
	const [isError, setIsError] = useState(false);

	useEffect(() => {
		let mounted = true;
		loadCurrentUser()
			.then((me) => {
				if (!mounted) return;
				setUser(me);
				setIsError(false);
				setIsLoading(false);
			})
			.catch(() => {
				if (!mounted) return;
				setIsError(true);
				setIsLoading(false);
			});

		return () => {
			mounted = false;
		};
	}, []);

	// force a fresh /users/me call, e.g. after a transient network failure
	const refresh = () => {
		cache = { status: "idle" };
		setIsError(false);
		setIsLoading(true);
		loadCurrentUser()
			.then((me) => {
				setUser(me);
				setIsLoading(false);
			})
			.catch(() => {
				setIsError(true);
				setIsLoading(false);
			});
	};

	const logout = async () => {
		try {
			await fetch("/api/auth/logout", { method: "POST" });
		} catch (err) {
			logError("Erreur lors de la déconnexion :", err);
		} finally {
			cache = { status: "idle" };
			// eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full reload to reset the in-memory user cache
			window.location.href = "/";
		}
	};

	return { user, role: user?.role ?? null, isLoading, isError, refresh, logout };
}
