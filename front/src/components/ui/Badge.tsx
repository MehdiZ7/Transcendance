import React from 'react';

export type BadgeVariant = 'default' | 'admin' | 'moderator' | 'success' | 'closed' | 'warning';

interface BadgeProps {
	children: React.ReactNode;
	className?: string;
	variant?: BadgeVariant;
}

const variantStyles: Record<BadgeVariant, string> = {
	default: "bg-gray-100 text-gray-800 border-gray-200",
	admin: "bg-purple-100 text-purple-800 border-purple-200",
	moderator: "bg-blue-100 text-blue-800 border-blue-200",
	success: "bg-emerald-100 text-emerald-800 border-emerald-200",
	warning: "bg-amber-100 text-amber-800 border-amber-200",
	closed: "bg-rose-100 text-rose-800 border-rose-200",
};

export function Badge ({children, variant = 'default', className=''}: BadgeProps) {
	const baseStyle = "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border";
	return (
		<span className={`${baseStyle} ${variantStyles[variant]} ${className}`}>
		{children}
		</span>
	);
}

