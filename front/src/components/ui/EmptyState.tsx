import { ReactNode } from 'react';

export interface EmptyStateProps {
	title: string;
	description: string;
	icon?: ReactNode;
	action?: ReactNode;
	className?: string;
}

export function EmptyState({
	title,
	description,
	icon,
	action,
	className = "",
}: EmptyStateProps) {
	return (
		<div className={`text-center py-12 px-4 bg-gray-50 rounded-xl border border-dashed border-gray-200 ${className}`}>
			{icon && (
				<div className="mx-auto flex items-center justify-center h-12 w-12 text-gray-400 mb-3">
					{icon}
				</div>
			)}
			<h3 className="text-base font-semibold text-gray-900">{title}</h3>
			<p className="mt-1 text-sm text-gray-500 max-w-sm mx-auto">{description}</p>
			{action && <div className="mt-5">{action}</div>}
		</div>
	);
}
