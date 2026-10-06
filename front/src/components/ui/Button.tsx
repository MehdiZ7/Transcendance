'use client';

import React from 'react';
import Link from 'next/link';

export type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

interface BaseButtonProps {
	variant?: ButtonVariant;
	size?: ButtonSize;
	fullWidth?: boolean;
	isLoading?: boolean;
	className?: string;
	children?: React.ReactNode;
}

export type ButtonProps = BaseButtonProps &
	(
		| (React.ButtonHTMLAttributes<HTMLButtonElement> & { href?: undefined })
		| (React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string })
	);

const VARIANTS: Record<ButtonVariant, string> = {
	primary:
		'bg-[#00babc] hover:bg-[#26e5e8] text-slate-950 font-bold shadow-xs hover:shadow-[0_0_20px_-3px_rgba(0,186,188,0.4)] active:scale-[0.98]',
	secondary:
		'bg-slate-100 hover:bg-slate-200 text-slate-800 font-semibold active:scale-[0.98]',
	outline:
		'border border-slate-200 hover:border-slate-300 hover:bg-slate-50 text-slate-700 font-semibold active:scale-[0.98]',
	ghost:
		'hover:bg-slate-100 text-slate-700 font-medium active:scale-[0.98]',
	danger:
		'bg-rose-500 hover:bg-rose-600 text-white font-bold shadow-xs active:scale-[0.98]',
};

const SIZES: Record<ButtonSize, string> = {
	sm: 'px-3.5 py-1.5 text-xs sm:text-sm rounded-xl gap-1.5',
	md: 'px-5 py-2.5 text-sm rounded-xl gap-2',
	lg: 'px-8 py-3 text-sm sm:text-base rounded-xl gap-2.5',
};

export const Button = React.forwardRef<HTMLButtonElement | HTMLAnchorElement, ButtonProps>(
	(
		{
			variant = 'primary',
			size = 'md',
			fullWidth = false,
			isLoading = false,
			className = '',
			children,
			...rest
		},
		ref
	) => {
		const baseClasses =
			'inline-flex items-center justify-center font-bold transition-all select-none cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed disabled:pointer-events-none';
		const variantClasses = VARIANTS[variant] || VARIANTS.primary;
		const sizeClasses = SIZES[size] || SIZES.md;
		const widthClass = fullWidth ? 'w-full' : '';

		const combinedClassName = [
			baseClasses,
			variantClasses,
			sizeClasses,
			widthClass,
			className,
		]
			.filter(Boolean)
			.join(' ');

		const content = (
			<>
				{isLoading && (
					<>
						<svg
							className="animate-spin -ml-1 mr-2 h-4 w-4 text-current"
							fill="none"
							viewBox="0 0 24 24"
							aria-hidden="true"
						>
							<circle
								className="opacity-25"
								cx="12"
								cy="12"
								r="10"
								stroke="currentColor"
								strokeWidth="4"
							/>
							<path
								className="opacity-75"
								fill="currentColor"
								d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
							/>
						</svg>
						<span className="sr-only">Chargement...</span>
					</>
				)}
				{children}
			</>
		);

		if ('href' in rest && typeof rest.href === 'string') {
			const { href, onClick, ...anchorProps } = rest;
			const isDisabled = isLoading;

			return (
				<Link
					href={isDisabled ? '#' : href}
					ref={ref as React.Ref<HTMLAnchorElement>}
					className={combinedClassName}
					aria-disabled={isDisabled}
					aria-busy={isLoading}
					tabIndex={isDisabled ? -1 : undefined}
					onClick={(e) => {
						if (isDisabled) {
							e.preventDefault();
							return;
						}
						onClick?.(e);
					}}
					{...anchorProps}
				>
					{content}
				</Link>
			);
		}

		const { type = 'button', ...buttonProps } = rest as React.ButtonHTMLAttributes<HTMLButtonElement>;

		return (
			<button
				ref={ref as React.Ref<HTMLButtonElement>}
				type={type}
				disabled={buttonProps.disabled || isLoading}
				className={combinedClassName}
				{...buttonProps}
			>
				{content}
			</button>
		);
	}
);

Button.displayName = 'Button';

export default Button;
