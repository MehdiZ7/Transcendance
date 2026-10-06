"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Card } from "@/components/ui/Card";
import { ConversationList, ChatWindow } from "@/components/messages";
import { usePresence } from "@/hooks/usePresence";
import { useMessages } from "@/hooks/useMessages";
import { AuthGuard } from "@/components/auth/AuthGuard";

function MessagesContent() {
  const searchParams = useSearchParams();
  const targetUserId = searchParams.get("user");
  const targetListingId = searchParams.get("listing_id");

  const { isOnline } = usePresence();

  const {
    loggedInUser,
    conversations,
    selectedConversationId,
    setSelectedConversationId,
    isLoading,
    error,
    newMessageBody,
    sendError,
    sendCooldown,
    setNewMessageBody,
    activeConversation,
    currentMessages,
    isMarkingSold,
    handleSelectConversation,
    handleSendMessage,
    handleMarkAsSold,
    handleReviewSubmitted,
    isOtherTyping,
    notifyTyping,
    hasMore,
    isLoadingMore,
    loadMoreError,
    handleLoadMore,
  } = useMessages(targetUserId, targetListingId);

  if (isLoading) {
    return (
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-sm text-gray-500 flex items-center justify-center min-h-[300px]">
        <div className="flex items-center gap-2">
          <svg className="animate-spin h-5 w-5 text-[#00babc]" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <span>Chargement des conversations…</span>
        </div>
      </main>
    );
  }

  if (error && conversations.length === 0) {
    return (
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-sm text-rose-600">
        {error}
      </main>
    );
  }

  return (
    <main className="max-w-7xl mx-auto px-0 sm:px-6 lg:px-8 py-0 sm:py-6">
      {error && (
        <div
          role="alert"
          className="m-2 sm:mb-4 sm:m-0 p-4 rounded-xl bg-rose-50 border border-rose-200 text-sm text-rose-700 font-medium flex items-center justify-between shadow-xs"
        >
          <span>{error}</span>
        </div>
      )}
      <Card className="p-0 h-[calc(100dvh-4rem)] sm:h-[calc(100vh-12rem)] sm:min-h-[500px] flex overflow-hidden border-0 sm:border rounded-none sm:rounded-2xl shadow-none sm:shadow-sm">
        {/* Left row : listing of message*/}
        <ConversationList
          conversations={conversations}
          selectedConversationId={selectedConversationId}
          onSelectConversation={handleSelectConversation}
          isOnline={isOnline}
        />

        {/* Right row: the discussion selected*/}
        <ChatWindow
          conversation={activeConversation}
          messages={currentMessages}
          currentUserId={loggedInUser?.id ?? ""}
          newMessageBody={newMessageBody}
          onChangeNewMessageBody={setNewMessageBody}
          onSendMessage={handleSendMessage}
          sendError={sendError}
          sendCooldown={sendCooldown}
          onBack={() => setSelectedConversationId(null)}
          onMarkAsSold={handleMarkAsSold}
          onReviewSubmitted={handleReviewSubmitted}
          isMarkingSold={isMarkingSold}
          isOtherTyping={isOtherTyping}
          onTyping={notifyTyping}
          hasMore={hasMore}
          isLoadingMore={isLoadingMore}
          loadMoreError={loadMoreError}
          onLoadMore={handleLoadMore}
        />
      </Card>
    </main>
  );
}

export default function MessagesPage() {
  return (
    <Suspense fallback={null}>
      <AuthGuard>
        <MessagesContent />
      </AuthGuard>
    </Suspense>
  );
}
