"use client";

import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Heading } from './Heading';
import { useIsMounted } from '@/hooks/useIsMounted';

interface ModalProps {
	isOpen: boolean;
	onClose: () => void;
	title?: string;
	children: React.ReactNode;
}

export function Modal({ isOpen, onClose, title, children }: ModalProps) {
	const mounted = useIsMounted();

	// Lock background page scroll while the modal is open
	useEffect(() => {
		if (isOpen) {
			const originalOverflow = document.body.style.overflow;
			document.body.style.overflow = 'hidden';
			return () => {
				document.body.style.overflow = originalOverflow;
			};
		}
	}, [isOpen]);

	// Close on the Escape key
	useEffect(() => {
		if (!isOpen) return;

		const handleKeyDown = (e: KeyboardEvent) => {
			if (e.key === 'Escape') {
				onClose();
			}
		};

		window.addEventListener('keydown', handleKeyDown);
		return () => window.removeEventListener('keydown', handleKeyDown);
	}, [isOpen, onClose]);

	if (!isOpen || !mounted) return null;

	return createPortal(
		<div
			className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-xs flex items-center justify-center p-4 text-slate-900"
			onClick={onClose}
			role="dialog"
			aria-modal="true"
		>
			{/* max-h-full + overflow: a modal taller than the screen (the profile
			    edit form with its password section) scrolls inside, instead of
			    losing its title and its last buttons out of reach (the page
			    itself cannot scroll while a modal is open) */}
			<div
				className="bg-white rounded-2xl shadow-2xl max-w-lg w-full max-h-full overflow-y-auto p-6 relative transition-all"
				onClick={(e) => e.stopPropagation()}
			>
				<div className="flex items-center justify-between border-b border-gray-100 pb-3 mb-4">
					{title && <Heading level={3}>{title}</Heading>}
					<button
						type="button"
						onClick={onClose}
						className="text-gray-400 hover:text-gray-600 rounded-lg p-1 hover:bg-gray-100 transition-colors cursor-pointer"
						aria-label="Fermer"
					>
						✕
					</button>
				</div>
				{children}
			</div>
		</div>,
		document.body
	);
}
