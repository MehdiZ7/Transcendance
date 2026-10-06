import React from 'react';

interface HeadingProps{
	level?: 1|2|3|4;
	children: React.ReactNode;
	className?: string;
}

export function Heading({ level = 1, children, className = '' }: HeadingProps) {
	const Tag = `h${level}` as keyof React.JSX.IntrinsicElements;

	const styles = {
		1: 'text-3xl font-extrabold text-gray-900 tracking-tight',
		2: 'text-2xl font-bold text-gray-800',
		3: 'text-xl font-semibold text-gray-800',
		4: 'text-lg font-medium text-gray-700',
	};

	return <Tag className={`${styles[level]} ${className}`}>{children}</Tag>;
}
