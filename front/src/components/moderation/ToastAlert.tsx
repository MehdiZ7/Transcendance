interface ToastAlertProps {
  message: string;
  onClose: () => void;
}

export function ToastAlert({ message, onClose }: ToastAlertProps) {
  return (
    <div className="bg-slate-900 text-white text-xs sm:text-sm px-4 py-3 rounded-xl shadow-md flex items-center justify-between gap-3 animate-in fade-in slide-in-from-top-2 duration-200">
      <div className="flex items-center gap-2">
        <svg
          className="w-4 h-4 text-[#00babc] shrink-0"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
        </svg>
        <span>{message}</span>
      </div>
      <button
        onClick={onClose}
        className="text-slate-400 hover:text-white transition-colors cursor-pointer"
        aria-label="Fermer la notification"
      >
        ✕
      </button>
    </div>
  );
}
