'use client';

import { Button } from '@/components/ui/Button';

export default function ExportPdfButton() {
  const handlePrint = () => {
    window.print();
  };

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={handlePrint}
      className="print:hidden inline-flex items-center gap-2 border-slate-300 bg-white hover:bg-slate-50 text-slate-700 shadow-2xs cursor-pointer"
      title="Exporter la page en PDF"
      aria-label="Exporter le rapport en PDF"
    >
      <svg
        className="w-4 h-4 text-slate-600"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"
        />
      </svg>
      <span>Exporter en PDF</span>
    </Button>
  );
}
