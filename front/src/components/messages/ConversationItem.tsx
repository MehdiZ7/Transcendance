import Image from "next/image";
import { Avatar } from "@/components/ui/Avatar";
import { isUnoptimizedImage } from "@/lib/images";
import type { ConversationSummary } from "@/types/message";

export interface ConversationItemProps {
  conversation: ConversationSummary;
  isSelected: boolean;
  onSelect: (id: string) => void;
  isOnline: (userId: string) => boolean;
}

export function ConversationItem({
  conversation,
  isSelected,
  onSelect,
  isOnline,
}: ConversationItemProps) {
  return (
    <button
      type="button"
      onClick={() => onSelect(conversation.id)}
      className={`w-full text-left p-4 flex items-start gap-3 hover:bg-gray-50 transition-colors ${
        isSelected ? "bg-purple-50/60 border-l-4 border-purple-600" : ""
      }`}
    >
      {conversation.listing_cover_image ? (
        <div className="w-12 h-12 rounded-lg overflow-hidden shrink-0 relative bg-gray-100">
          <Image
            src={conversation.listing_cover_image}
            alt={conversation.listing_title ?? conversation.other_participant.display_name}
            fill
            unoptimized={isUnoptimizedImage(conversation.listing_cover_image)}
            sizes="48px"
            className="object-cover"
          />
        </div>
      ) : (
        <Avatar
          src={conversation.other_participant.avatar_path ?? undefined}
          alt={conversation.other_participant.display_name}
          size="md"
        />
      )}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1 gap-2">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-sm font-semibold text-gray-900 truncate">
              {conversation.other_participant.display_name}
            </span>
            {isOnline(conversation.other_participant.id) ? (
              <span className="shrink-0 text-[10px] font-semibold text-emerald-600">
                ● En ligne
              </span>
            ) : (
              <span className="shrink-0 text-[10px] font-semibold text-rose-500">
                ● Hors ligne
              </span>
            )}
          </div>
          {conversation.last_message && (
            <span className="text-xs text-gray-400 shrink-0">
              {new Date(conversation.last_message.created_at).toLocaleTimeString("fr-FR", {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          )}
        </div>
        {conversation.listing_title ? (
          <p className="text-xs text-purple-600 font-medium truncate mb-1">
            📌 {conversation.listing_title}
          </p>
        ) : (
          <p className="text-xs text-blue-600 font-medium truncate mb-1">
            💬 Discussion directe
          </p>
        )}
        <div className="flex items-center justify-between gap-2">
          <p className={`text-xs truncate flex-1 ${conversation.last_message?.deleted_at ? "text-gray-400 italic" : "text-gray-500"}`}>
            {conversation.last_message?.deleted_at
              ? "Message supprimé"
              : conversation.last_message?.body ?? "Nouvelle discussion"}
          </p>
          {conversation.unread_count > 0 && (
            <span className="shrink-0 bg-purple-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full">
              {conversation.unread_count}
            </span>
          )}
        </div>
      </div>
    </button>
  );
}
