import type { ModerationCounts, ModerationTab } from './types';

interface ModerationTabsProps {
  activeTab: ModerationTab;
  onTabChange: (tab: ModerationTab) => void;
  counts: ModerationCounts;
  showHistory?: boolean;
  showAdminUsers?: boolean;
}

export function ModerationTabs({
  activeTab,
  onTabChange,
  counts,
  showHistory = false,
  showAdminUsers = false,
}: ModerationTabsProps) {
  return (
    <div className="border-b border-slate-200">
      <nav
        className="flex items-center gap-2 sm:gap-4 overflow-x-auto no-scrollbar -mb-px w-full"
        aria-label="Onglets de modération"
      >
        {/* Listings tab */}
        <button
          type="button"
          onClick={() => onTabChange('listings')}
          className={`flex items-center gap-2 py-3.5 px-4 font-semibold text-sm border-b-2 transition-all cursor-pointer whitespace-nowrap ${activeTab === 'listings'
              ? 'border-[#00babc] text-slate-900 bg-teal-50/40 rounded-t-lg'
              : 'border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300'
            }`}
        >
          <svg
            className={`w-4 h-4 ${activeTab === 'listings' ? 'text-[#00babc]' : 'text-slate-400'
              }`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
            />
          </svg>
          <span>Annonces</span>
          <span
            className={`text-xs font-bold px-2 py-0.5 rounded-full transition-colors ${activeTab === 'listings'
                ? 'bg-[#00babc] text-slate-950 font-extrabold'
                : 'bg-slate-100 text-slate-600'
              }`}
          >
            {counts.listings}
          </span>
        </button>

        {/* Messages tab */}
        <button
          type="button"
          onClick={() => onTabChange('messages')}
          className={`flex items-center gap-2 py-3.5 px-4 font-semibold text-sm border-b-2 transition-all cursor-pointer whitespace-nowrap ${activeTab === 'messages'
              ? 'border-[#00babc] text-slate-900 bg-teal-50/40 rounded-t-lg'
              : 'border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300'
            }`}
        >
          <svg
            className={`w-4 h-4 ${activeTab === 'messages' ? 'text-[#00babc]' : 'text-slate-400'
              }`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a.75.75 0 01-.818-.68 5.753 5.753 0 01.597-2.738C3.81 16.035 3 14.125 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z"
            />
          </svg>
          <span>Messages</span>
          <span
            className={`text-xs font-bold px-2 py-0.5 rounded-full transition-colors ${activeTab === 'messages'
                ? 'bg-[#00babc] text-slate-950 font-extrabold'
                : 'bg-slate-100 text-slate-600'
              }`}
          >
            {counts.messages}
          </span>
        </button>

        {/* Users tab */}
        <button
          type="button"
          onClick={() => onTabChange('users')}
          className={`flex items-center gap-2 py-3.5 px-4 font-semibold text-sm border-b-2 transition-all cursor-pointer whitespace-nowrap ${activeTab === 'users'
              ? 'border-[#00babc] text-slate-900 bg-teal-50/40 rounded-t-lg'
              : 'border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300'
            }`}
        >
          <svg
            className={`w-4 h-4 ${activeTab === 'users' ? 'text-[#00babc]' : 'text-slate-400'
              }`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z"
            />
          </svg>
          <span>Utilisateurs</span>
          <span
            className={`text-xs font-bold px-2 py-0.5 rounded-full transition-colors ${activeTab === 'users'
                ? 'bg-[#00babc] text-slate-950 font-extrabold'
                : 'bg-slate-100 text-slate-600'
              }`}
          >
            {counts.users}
          </span>
        </button>

        {/* Reviews tab */}
        <button
          type="button"
          onClick={() => onTabChange('reviews')}
          className={`flex items-center gap-2 py-3.5 px-4 font-semibold text-sm border-b-2 transition-all cursor-pointer whitespace-nowrap ${activeTab === 'reviews'
              ? 'border-[#00babc] text-slate-900 bg-teal-50/40 rounded-t-lg'
              : 'border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300'
            }`}
        >
          <svg
            className={`w-4 h-4 ${activeTab === 'reviews' ? 'text-[#00babc]' : 'text-slate-400'
              }`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z"
            />
          </svg>
          <span>Avis</span>
          <span
            className={`text-xs font-bold px-2 py-0.5 rounded-full transition-colors ${activeTab === 'reviews'
                ? 'bg-[#00babc] text-slate-950 font-extrabold'
                : 'bg-slate-100 text-slate-600'
              }`}
          >
            {counts.reviews}
          </span>
        </button>

        {/* Account management tab (admin only) */}
        {showAdminUsers && (
          <button
            type="button"
            onClick={() => onTabChange('admin-users')}
            className={`flex items-center gap-2 py-3.5 px-4 font-semibold text-sm border-b-2 transition-all cursor-pointer whitespace-nowrap ${
              activeTab === 'admin-users'
                ? 'border-[#00babc] text-slate-900 bg-teal-50/40 rounded-t-lg'
                : 'border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300'
            }`}
          >
            <svg
              className={`w-4 h-4 ${
                activeTab === 'admin-users' ? 'text-[#00babc]' : 'text-slate-400'
              }`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z"
              />
            </svg>
            <span>Gestion des comptes</span>
          </button>
        )}

        {/* Historique Tab */}
        {showHistory && (
          <button
            type="button"
            onClick={() => onTabChange('history')}
            className={`flex items-center gap-2 py-3.5 px-4 font-semibold text-sm border-b-2 transition-all cursor-pointer whitespace-nowrap ${activeTab === 'history'
                ? 'border-[#00babc] text-slate-900 bg-teal-50/40 rounded-t-lg'
                : 'border-transparent text-slate-600 hover:text-slate-900 hover:border-slate-300'
              }`}
          >
            <svg
              className={`w-4 h-4 ${activeTab === 'history' ? 'text-[#00babc]' : 'text-slate-400'
                }`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>Historique</span>
          </button>
        )}
      </nav>
    </div>
  );
}
