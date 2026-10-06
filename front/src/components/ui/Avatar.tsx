interface AvatarProps {
	src?: string | null;
	alt: string;
	size?: 'sm' | 'md' | 'lg' | 'xl';
	className?: string;
}

const sizeStyles = {
	sm: 'w-8 h-8 text-xs',
	md: 'w-12 h-12 text-sm',
	lg: 'w-20 h-20 text-lg',
	xl: 'w-32 h-32 text-2xl',
}

function getInitials(name: string) : string {
	if (!name) return '?';
	const parts = name.trim().split(' ');
	if (parts.length >= 2){
		return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
	}
	return name.slice(0,2).toUpperCase();
}

export function Avatar({src, alt, size = 'xl', className=''}: AvatarProps) {
	const sizeClass = sizeStyles[size];
	if (!src){
		return (
			<div
			className={`flex items-center justify-center rounded-full bg-purple-600 text-white font-bold select-none ${sizeClass} ${className}`}
			aria-label={alt}
			>
				{getInitials(alt)}
			</div>
		);
	}

	return (
		// eslint-disable-next-line @next/next/no-img-element -- avatars come from arbitrary storage paths; next/image would need remotePatterns
		<img
		src={src}
		alt={alt}
		className={`rounded-full object-cover ${sizeClass} ${className}`}
		/>
	);
}

