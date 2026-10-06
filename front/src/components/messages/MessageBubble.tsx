import type { Message } from "@/types/message";
import { ReportButton } from "@/components/ui/ReportModal";
import { reportsApi } from "@/lib/api/reports";
export interface MessageBubbleProps {
  message: Message;
  isMe: boolean;
  isDirect: boolean;
}

export function MessageBubble({ message, isMe, isDirect }: MessageBubbleProps) {
  const isDeleted = Boolean(message.deleted_at);
  const isEdited = Boolean(message.edited_at) && !isDeleted;

  return (
    <div className={`group relative flex items-end gap-1 ${isMe ? "justify-end" : "justify-start"}`}>
      {!isMe && !isDeleted && !isDirect && (
        <ReportButton
          targetType="message"
          targetId={String(message.id)}
          label="Signaler ce message"
          variant="icon"
          className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0 self-end mb-0.5"
          onSubmit={async (data) => {
            await reportsApi.create({ ...data, target_id: String(data.target_id) }, { target: message });
          }}
        />
      )}

      <div
        className={`max-w-[75%] min-w-0 rounded-2xl px-4 py-2.5 text-sm shadow-sm ${isMe
          ? isDirect
            ? "bg-blue-600 text-white rounded-br-none"
            : "bg-purple-600 text-white rounded-br-none"
          : "bg-white border border-gray-200 text-gray-800 rounded-bl-none"
          }`}
      >
        <p className={`leading-relaxed whitespace-pre-wrap break-words ${isDeleted ? "italic opacity-70" : ""}`}>
          {isDeleted ? "Message supprimé" : message.body}
        </p>
        <span
          className={`block text-[10px] mt-1 text-right ${isMe ? (isDirect ? "text-blue-200" : "text-purple-200") : "text-gray-400"
            }`}
        >
          {isEdited && <span className="mr-1">modifié</span>}
          {new Date(message.created_at).toLocaleTimeString("fr-FR", {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      </div>
    </div>
  );
}
