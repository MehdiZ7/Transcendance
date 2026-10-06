import React from 'react';
import { cn } from '@/lib/utils';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  className?: string;
}

export function Card({ children, className = '', ...props }: CardProps) {
  return (
    <div className={cn('bg-white border border-gray-200 rounded-2xl shadow-sm p-6', className)} {...props}>
      {children}
    </div>
  );
}
