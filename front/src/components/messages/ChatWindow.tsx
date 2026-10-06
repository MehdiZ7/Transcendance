import { Fragment, useEffect, useRef, useState } from "react";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { ChatHeader } from "./ChatHeader";
import { TransactionBanner } from "./TransactionBanner";
import { ReviewModal } from "@/components/reviews";
import { MessageBubble } from "./MessageBubble";
import { MessageInput } from "./MessageInput";
import type { InboxConversation, Message } from "@/types/message";
import type { Review } from "@/types/report";

function isDifferentDay(d1Str?: string, d2Str?: string): boolean {
  if (!d1Str || !d2Str) return true;
  const d1 = new Date(d1Str);
  const d2 = new Date(d2Str);
  return (
    d1.getFullYear() !== d2.getFullYear() ||
    d1.getMonth() !== d2.getMonth() ||
    d1.getDate() !== d2.getDate()
  );
}

function formatDateSeparator(dateStr: string): string {
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return "";

  const now = new Date();
  const startOfDate = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const oneDayMs = 24 * 60 * 60 * 1000;
  const diffDays = Math.round((startOfToday - startOfDate) / oneDayMs);

  if (diffDays === 0) {
    return "Aujourd'hui";
  }
  if (diffDays === 1) {
    return "Hier";
  }

  const isSameYear = date.getFullYear() === now.getFullYear();
  const formatted = date.toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "long",
    year: isSameYear ? undefined : "numeric",
  });

  return formatted.charAt(0).toUpperCase() + formatted.slice(1);
}

export interface ChatWindowProps {
  conversation: InboxConversation | null;
  messages: Message[];
  currentUserId: string;
  newMessageBody: string;
  onChangeNewMessageBody: (value: string) => void;
  onSendMessage: (e: React.FormEvent) => void;
  sendError?: string | null;
  sendCooldown?: number;
  onBack: () => void;
  onMarkAsSold?: (conversationId: string) => Promise<void> | void;
  onReviewSubmitted?: (conversationId: string, review: Review) => void;
  isMarkingSold?: boolean;
  isOtherTyping?: boolean;
  onTyping?: () => void;
  hasMore?: boolean;
  isLoadingMore?: boolean;
  loadMoreError?: string | null;
  onLoadMore?: () => void;
}

export function ChatWindow({
  conversation,
  messages,
  currentUserId,
  newMessageBody,
  onChangeNewMessageBody,
  onSendMessage,
  sendError,
  sendCooldown,
  onBack,
  onMarkAsSold,
  onReviewSubmitted,
  isMarkingSold,
  isOtherTyping,
  onTyping,
  hasMore,
  isLoadingMore,
  loadMoreError,
  onLoadMore,
}: ChatWindowProps) {
  const [isReviewModalOpen, setIsReviewModalOpen] = useState(false);

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const lastMessageId = messages[messages.length - 1]?.id;

  // Stay at the bottom: on conversation open and on every new message.
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [conversation?.id, lastMessageId, isOtherTyping]);

  return (
    <section
      className={`flex-1 min-w-0 flex flex-col bg-white ${!conversation ? "hidden md:flex" : "flex"
        }`}
    >
      {conversation ? (
        <>
          {/* Chat header */}
          <ChatHeader
            participant={conversation.other_participant}
            listingTitle={conversation.listing_title}
            listingHref={
              conversation.listing_status?.toLowerCase() === "deleted"
                ? null
                : conversation.listing_public_id ?? conversation.listing_id
                ? `/listings/${conversation.listing_public_id ?? conversation.listing_id}`
                : null
            }
            onBack={onBack}
          />

          {/* Transaction status & action banner */}
          <TransactionBanner
            conversation={conversation}
            currentUserId={currentUserId}
            onMarkAsSold={(convId) => onMarkAsSold?.(convId)}
            onOpenReviewModal={() => setIsReviewModalOpen(true)}
            isMarkingSold={isMarkingSold}
          />

          {/* Modal for leaving a review */}
          {isReviewModalOpen && (
            <ReviewModal
              isOpen={isReviewModalOpen}
              onClose={() => setIsReviewModalOpen(false)}
              conversationId={conversation.rawId}
              seller={conversation.other_participant}
              listingTitle={conversation.listing_title}
              onSuccess={(review) => {
                onReviewSubmitted?.(conversation.id, review);
              }}
            />
          )}

          {/* Message area */}
          <div ref={scrollContainerRef} className="flex-1 p-4 overflow-y-auto space-y-4 bg-gray-50/30">
            {hasMore && (
              <div className="flex flex-col items-center gap-1.5">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={onLoadMore}
                  isLoading={isLoadingMore}
                  disabled={isLoadingMore}
                >
                  Charger les messages plus anciens
                </Button>
                {loadMoreError && (
                  <p role="alert" className="text-xs text-rose-600 font-medium">
                    {loadMoreError}
                  </p>
                )}
              </div>
            )}
            {messages.map((msg, index) => {
              const previousMsg = index > 0 ? messages[index - 1] : undefined;
              const showDateSeparator =
                !previousMsg || isDifferentDay(previousMsg.created_at, msg.created_at);

              return (
                <Fragment key={msg.id}>
                  {showDateSeparator && (
                    <div className="flex items-center my-3 select-none" aria-hidden="true">
                      <div className="flex-grow border-t border-gray-200/80"></div>
                      <span className="shrink-0 mx-4 px-3 py-0.5 bg-gray-100 text-gray-500 text-xs font-medium rounded-full border border-gray-200 shadow-2xs">
                        {formatDateSeparator(msg.created_at)}
                      </span>
                      <div className="flex-grow border-t border-gray-200/80"></div>
                    </div>
                  )}
                  <MessageBubble
                    message={msg}
                    isMe={msg.sender_id === currentUserId}
                    isDirect={!conversation.listing_title}
                  />
                </Fragment>
              );
            })}
            {isOtherTyping && (
              <div className="flex justify-start">
                <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-none px-4 py-3 shadow-sm">
                  <span className="flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:-0.3s]" />
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:-0.15s]" />
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce" />
                  </span>
                </div>
              </div>
            )}
          </div>

          {sendError && (
            <p
              role="alert"
              className={`px-4 py-2 text-sm border-t ${
                sendCooldown && sendCooldown > 0
                  ? "text-amber-800 bg-amber-50 border-amber-200"
                  : "text-red-600 bg-red-50 border-red-100"
              }`}
            >
              {sendError}
            </p>
          )}

          {/* Input message area*/}
          <MessageInput
            value={newMessageBody}
            onChange={onChangeNewMessageBody}
            onTyping={onTyping}
            onSubmit={onSendMessage}
            disabled={conversation.is_closed}
            cooldown={sendCooldown}
          />
        </>
      ) : (
        <div className="flex-1 flex items-center justify-center p-6">
          <EmptyState
            title="Aucune discussion sélectionnée"
            description="Choisissez une conversation dans la liste de gauche pour afficher les messages."
          />
        </div>
      )}
    </section>
  );
}
