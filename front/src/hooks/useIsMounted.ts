"use client";

import { useSyncExternalStore } from "react";

const emptySubscribe = () => () => {};

/**
 * True on the client once hydrated, false during SSR and the first client
 * render. Use it to guard client-only rendering (portals, hydration-sensitive
 * attributes) without calling setState inside an effect.
 */
export function useIsMounted(): boolean {
	return useSyncExternalStore(emptySubscribe, () => true, () => false);
}
