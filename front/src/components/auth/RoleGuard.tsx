"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import type { UserRole } from "@/types/user";
import { useCurrentUser } from "@/hooks/useCurrentUser";

export function RoleGuard({
	allowed,
	children,
}: {
	allowed: UserRole[];
	children: React.ReactNode;
}) {
	const router = useRouter();
	const { role, isLoading } = useCurrentUser();

	useEffect(() => {
		if (!isLoading && (!role || !allowed.includes(role))) {
			router.replace("/");
		}
	}, [isLoading, role, allowed, router]);

	if (isLoading) {
		return (
			<main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-sm text-gray-500">
				Chargement…
			</main>
		);
	}

	if (!role || !allowed.includes(role)) {
		return null;
	}
	return <>{children}</>;
}
