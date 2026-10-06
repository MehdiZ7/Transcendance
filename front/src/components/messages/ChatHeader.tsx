import Link from "next/link";
import { Avatar } from "@/components/ui/Avatar";
import type { PublicUser } from "@/types/user";

export interface ChatHeaderProps {
  participant: PublicUser;
  listingTitle?: string | null;
  listingHref?: string | null;
  onBack: () => void;
}

export function ChatHeader({
  participant,
  listingTitle,
  listingHref,
  onBack,
}: ChatHeaderProps) {
  return (
    <header className="px-3 sm:px-4 py-3 border-b border-gray-200 flex items-center justify-between bg-white shrink-0">
      <div className="flex items-center gap-2 sm:gap-3 min-w-0 flex-1">
        {/* Back button for mobile */}
        <button
          type="button"
          onClick={onBack}
          aria-label="Retour à la liste des discussions"
          className="md:hidden p-2 -ml-1 text-gray-700 hover:text-gray-900 hover:bg-gray-100 active:bg-gray-200 rounded-lg transition-colors shrink-0 flex items-center justify-center cursor-pointer"
        >
          <svg
            className="w-5 h-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2.5}
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
        </button>
        <Avatar
          src={participant.avatar_path ?? undefined}
          alt={participant.display_name}
          size="sm"
          className="shrink-0"
        />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-gray-900 truncate">
            {participant.display_name}
          </p>
          {listingTitle ? (
            listingHref ? (
              <Link
                href={listingHref}
                className="text-xs text-purple-600 font-medium hover:text-purple-800 hover:underline truncate block"
              >
                {listingTitle}
              </Link>
            ) : (
              <p className="text-xs text-slate-500 font-medium truncate">
                {listingTitle}
              </p>
            )
          ) : (
            <p className="text-xs my-0.5 text-blue-500 font-medium truncate">
              Discussion directe
            </p>
          )}
        </div>
      </div>
    </header>
  );
}
