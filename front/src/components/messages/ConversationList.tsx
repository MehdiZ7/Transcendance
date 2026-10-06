import { Heading } from "@/components/ui/Heading";
import { ConversationItem } from "./ConversationItem";
import type { ConversationSummary } from "@/types/message";

export interface ConversationListProps {
  conversations: ConversationSummary[];
  selectedConversationId: string | null;
  onSelectConversation: (id: string) => void;
  isOnline: (userId: string) => boolean;
}

export function ConversationList({
  conversations,
  selectedConversationId,
  onSelectConversation,
  isOnline,
}: ConversationListProps) {
  return (
    <aside
      className={`w-full md:w-80 lg:w-96 border-r-0 md:border-r border-gray-200 flex flex-col bg-white ${
        selectedConversationId ? "hidden md:flex" : "flex"
      }`}
    >
      <div className="p-4 border-b border-gray-100 bg-gray-50/50 flex items-center justify-between shrink-0">
        <Heading level={3} className="text-sm font-semibold text-gray-500 uppercase tracking-wider">
          Discussions
        </Heading>
        {conversations.length > 0 && (
          <span className="text-xs font-semibold text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
            {conversations.length}
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto divide-y divide-gray-100">
        {conversations.length === 0 ? (
          <div className="p-8 text-center flex flex-col items-center justify-center h-full min-h-[200px]">
            <span className="text-3xl mb-2" aria-hidden="true">
              💬
            </span>
            <p className="text-sm font-medium text-gray-600">Aucune discussion</p>
            <p className="text-xs text-gray-400 mt-1 max-w-[220px]">
              Vos échanges avec les vendeurs et acheteurs apparaîtront ici.
            </p>
          </div>
        ) : (
          conversations.map((conv) => (
            <ConversationItem
              key={conv.id}
              conversation={conv}
              isSelected={conv.id === selectedConversationId}
              onSelect={onSelectConversation}
              isOnline={isOnline}
            />
          ))
        )}
      </div>
    </aside>
  );
}
