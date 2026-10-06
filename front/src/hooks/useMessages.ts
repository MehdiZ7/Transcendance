"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import type {
  ConversationSummary,
  FriendConversationSummary,
  FriendMessage,
  InboxConversation,
  InboxKind,
  Message,
} from "@/types/message";
import type { UserProfile } from "@/types/user";
import { usersApi } from "@/lib/api/users";
import { conversationsApi, messagesApi } from "@/lib/api/messages";
import { friendsApi } from "@/lib/api/friends";
import { ApiError } from "@/lib/api/client";
import { logError } from "@/lib/log";
import { useRealtimeSend, useRealtimeTopic } from "@/lib/realtime/hooks";
import {
  userTopic,
  type FriendMessageCreatedPayload,
  type FriendTypingPayload,
  type MessageCreatedPayload,
  type TypingPayload,
} from "@/lib/realtime/topics";

import type { Review } from "@/types/report";

const TYPING_EXPIRY_MS = 5000;
// matches the API default page size (GET .../messages return the latest 30)
const MESSAGES_PAGE_SIZE = 30;

// listing conversations and friend conversations share one inbox, keyed "kind:id"
const listingKey = (id: string | number) => `listing:${id}`;
const friendKey = (id: string | number) => `friend:${id}`;

function listingToInbox(conversation: ConversationSummary): InboxConversation {
  return {
    ...conversation,
    id: listingKey(conversation.id),
    rawId: String(conversation.id),
    kind: "listing",
  };
}

function friendToInbox(thread: FriendConversationSummary): InboxConversation {
  const key = friendKey(thread.friend_id);
  return {
    id: key,
    rawId: String(thread.friend_id),
    kind: "friend",
    listing_id: null,
    listing_public_id: null,
    listing_title: null,
    listing_cover_image: null,
    other_participant: thread.other_participant,
    last_message: thread.last_message
      ? friendMessageToDisplay(thread.last_message, key)
      : null,
    unread_count: thread.unread_count,
    is_closed: false,
    updated_at: thread.updated_at,
    listing_status: null,
    listing_seller_id: null,
    listing_buyer_id: null,
    has_reviewed: false,
  };
}

// a friend message as MessageBubble expects it (conversation_id is the inbox key)
function friendMessageToDisplay(message: FriendMessage, key: string): Message {
  return {
    id: String(message.id),
    conversation_id: key,
    sender_id: String(message.sender_id),
    body: message.body,
    created_at: message.created_at,
    edited_at: message.edited_at ?? null,
    deleted_at: message.deleted_at ?? null,
  };
}

async function fetchInbox(): Promise<InboxConversation[]> {
  const [listing, friend] = await Promise.all([
    conversationsApi.list(),
    friendsApi.listConversations(),
  ]);
  return [...listing.map(listingToInbox), ...friend.map(friendToInbox)].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  );
}

export function useMessages(targetUserId: string | null, targetListingId: string | null) {
  const [loggedInUser, setLoggedInUser] = useState<UserProfile | null>(null);
  const [conversations, setConversations] = useState<InboxConversation[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Record<string, Message[]>>({});
  const [hasMore, setHasMore] = useState<Record<string, boolean>>({});
  const [isLoadingMore, setIsLoadingMore] = useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [sendError, setSendError] = useState<string | null>(null);
  const [sendCooldown, setSendCooldown] = useState<number>(0);
  const [isMarkingSold, setIsMarkingSold] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  //typing indicator :
  const [typingConversations, setTypingConversation] = useState<Record<string, boolean>>({});
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const typingSentAtRef = useRef(0);
  // conversation the server currently believes we are typing in (a `true` with no `false` yet)
  const typingSentRef = useRef<{ kind: InboxKind; id: number; topic: ReturnType<typeof userTopic> } | null>(null);
  // "typing…" shown for the other side, one expiry timer per conversation
  const typingExpiryRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const sendRealtime = useRealtimeSend();
  // message.created events received for a conversation whose history is not loaded yet
  const earlyMessagesRef = useRef<Record<string, Message[]>>({});
  // latest conversations, for the realtime handler
  const conversationsRef = useRef<InboxConversation[]>([]);
  const attemptedListingRef = useRef<string | null>(null);

  useEffect(() => {
    conversationsRef.current = conversations;
  }, [conversations]);

  // Décompte pour le rate-limit d'envoi de messages (HTTP 429)
  useEffect(() => {
    if (sendCooldown <= 0) return;

    const timer = setInterval(() => {
      setSendCooldown((prev) => {
        if (prev <= 1) {
          setSendError((curr) =>
            curr && curr.includes("trop rapidement") ? null : curr
          );
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [sendCooldown]);

  const reloadInbox = useCallback(() => {
    fetchInbox()
      .then(setConversations)
      .catch((err) => {
        logError("Erreur lors du rechargement de la boîte de réception :", err);
      });
  }, []);

  // load the current user and the conversations
  useEffect(() => {
    let cancelled = false;
    Promise.all([usersApi.getCurrent(), fetchInbox()])
      .then(([me, inbox]) => {
        if (cancelled) return;
        setLoggedInUser(me);
        setConversations(inbox);
        const match = inbox.find(
          (c) =>
            (targetListingId &&
              c.kind === "listing" &&
              (c.listing_id === targetListingId || c.listing_public_id === targetListingId)) ||
            (targetUserId &&
              c.kind === "friend" &&
              (c.other_participant.id === targetUserId ||
                c.other_participant.public_id === targetUserId)),
        );
        const isDesktop = typeof window !== "undefined" && window.innerWidth >= 768;
        setSelectedConversationId(match?.id ?? (isDesktop ? inbox[0]?.id ?? null : null));
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Impossible de charger les conversations");
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [targetUserId, targetListingId]);

  // create or open a conversation linked to a listing when reaching via ?listing_id=
  useEffect(() => {
    if (isLoading) return;
    if (!targetListingId) return;
    if (attemptedListingRef.current === targetListingId) return;

    const existing = conversations.find(
      (c) =>
        c.kind === "listing" &&
        (c.listing_id === targetListingId || c.listing_public_id === targetListingId),
    );
    if (existing) {
      attemptedListingRef.current = targetListingId;
      return;
    }

    attemptedListingRef.current = targetListingId;
    let cancelled = false;
    (async () => {
      try {
        const conversation = await conversationsApi.getOrCreateListing(targetListingId);
        if (cancelled || !conversation) return;

        const inbox = listingToInbox(conversation);
        setConversations((prev) => [inbox, ...prev.filter((c) => c.id !== inbox.id)]);
        setSelectedConversationId(inbox.id);
      } catch (err) {
        if (!cancelled) {
          logError("Erreur lors de l'ouverture de la conversation :", err);
          setError(
            err instanceof Error
              ? err.message
              : "Impossible d'ouvrir la conversation pour cette annonce",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoading, targetListingId, conversations]);

  // lazy-load the messages of the selected conversation
  useEffect(() => {
    if (!selectedConversationId) return;
    if (messages[selectedConversationId]) return;

    const conversation = conversations.find((c) => c.id === selectedConversationId);
    if (!conversation) return;

    let cancelled = false;
    (async () => {
      try {
        let fetched: Message[];
        if (conversation.kind === "listing") {
          fetched = await messagesApi.list(conversation.rawId);
        } else {
          const raw = await friendsApi.listMessages(conversation.other_participant.public_id);
          fetched = raw.map((m) => friendMessageToDisplay(m, conversation.id));
        }
        if (cancelled) return;
        // events that arrived while this request was in flight may be missing
        // from `fetched`: add them, once
        const early = earlyMessagesRef.current[selectedConversationId] ?? [];
        delete earlyMessagesRef.current[selectedConversationId];
        const msgs = [
          ...fetched,
          ...early.filter((e) => !fetched.some((m) => String(m.id) === String(e.id))),
        ];
        setMessages((prev) => ({ ...prev, [selectedConversationId]: msgs }));
        setHasMore((prev) => ({ ...prev, [selectedConversationId]: fetched.length >= MESSAGES_PAGE_SIZE }));
      } catch (err) {
        if (!cancelled) {
          logError("Erreur lors du chargement des messages :", err);
          setSendError(
            err instanceof Error ? err.message : "Impossible de charger les messages",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedConversationId, messages, conversations]);

  // The other side re-sends `true` every 1.5 s while typing, so a `true` not
  // renewed within TYPING_EXPIRY_MS means the `false` was lost (closed tab, dropped link)
  const setOtherTyping = (key: string, isTyping: boolean) => {
    const timers = typingExpiryRef.current;
    if (timers[key]) {
      clearTimeout(timers[key]);
      delete timers[key];
    }
    setTypingConversation((prev) => ({ ...prev, [key]: isTyping }));
    if (isTyping) {
      timers[key] = setTimeout(() => {
        delete timers[key];
        setTypingConversation((prev) => ({ ...prev, [key]: false }));
      }, TYPING_EXPIRY_MS);
    }
  };

  const clearTypingExpiry = () => {
    Object.values(typingExpiryRef.current).forEach(clearTimeout);
    typingExpiryRef.current = {};
  };

  // append a message to its conversation and update the inbox
  const ingestMessage = (key: string, message: Message) => {
    setMessages((prev) => {
      const list = prev[key];
      if (!list) {
        // not loaded yet: keep it for when the load finishes, which may have
        // been answered before this message existed (idempotent: updaters can run twice)
        const early = (earlyMessagesRef.current[key] ??= []);
        if (!early.some((m) => String(m.id) === String(message.id))) early.push(message);
        return prev;
      }
      // already there: our own REST reply
      if (list.some((m) => String(m.id) === String(message.id))) return prev;
      return { ...prev, [key]: [...list, message] };
    });
    setOtherTyping(key, false);

    if (!conversationsRef.current.some((c) => c.id === key)) {
      // a conversation someone just opened with us
      reloadInbox();
      return;
    }
    const fromOther = String(message.sender_id) !== String(loggedInUser?.id);
    setConversations((prev) =>
      prev.map((conv) =>
        conv.id === key
          ? {
              ...conv,
              last_message: message,
              updated_at: message.created_at,
              unread_count:
                fromOther && selectedConversationId !== key
                  ? conv.unread_count + 1
                  : conv.unread_count,
            }
          : conv,
      ),
    );
  };

  // receive new messages and typing events in real time, on the user's own topic
  useRealtimeTopic(
    loggedInUser ? userTopic(loggedInUser.id) : null,
    (event) => {
      switch (event.type) {
        case "message.created": {
          const msg = event.payload as unknown as MessageCreatedPayload;
          ingestMessage(listingKey(msg.conversation_id), msg);
          return;
        }
        case "friend_message.created": {
          const fm = event.payload as unknown as FriendMessageCreatedPayload;
          ingestMessage(friendKey(fm.friend_id), friendMessageToDisplay(fm, friendKey(fm.friend_id)));
          return;
        }
        case "typing": {
          const { conversation_id, user_id, is_typing } = event.payload as unknown as TypingPayload;
          //we are ignoring our own events
          if (user_id === loggedInUser?.id) return;
          setOtherTyping(listingKey(conversation_id), is_typing);
          return;
        }
        case "friend_typing": {
          const { friend_id, user_id, is_typing } = event.payload as unknown as FriendTypingPayload;
          if (user_id === loggedInUser?.id) return;
          setOtherTyping(friendKey(friend_id), is_typing);
          return;
        }
      }
    },
    {
      // events may have been lost while disconnected: reload over HTTP
      onReset: () => {
        reloadInbox();
        setMessages({});
        earlyMessagesRef.current = {};
        clearTypingExpiry();
        setTypingConversation({});
      },
    },
  );

  // Tell the server we stopped typing, if it still thinks we are
  const stopTyping = useCallback(() => {
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
      typingTimeoutRef.current = null;
    }
    typingSentAtRef.current = 0;
    const sent = typingSentRef.current;
    typingSentRef.current = null;
    if (sent) {
      const payload = sent.kind === "listing"
        ? { conversation_id: sent.id, is_typing: false }
        : { friend_id: sent.id, is_typing: false };
      sendRealtime(sent.kind === "listing" ? "typing" : "friend_typing", sent.topic, payload);
    }
  }, [sendRealtime]);

  // Leaving the conversation (or the page) while typing: send the `false` now
  useEffect(() => stopTyping, [selectedConversationId, stopTyping]);

  //cleaning the timers
  useEffect(() => {
    return () => {
      Object.values(typingExpiryRef.current).forEach(clearTimeout);
    };
  }, []);

  const activeConversation = conversations.find((c) => c.id === selectedConversationId) ?? null;
  const currentMessages = selectedConversationId ? messages[selectedConversationId] ?? [] : [];
  const isOtherTyping = activeConversation ? Boolean(typingConversations[activeConversation.id]) : false;

  const newMessageBody = selectedConversationId ? drafts[selectedConversationId] ?? "" : "";

  const updateDraft = useCallback(
    (conversationId: string, value: string | ((prev: string) => string)) => {
      setDrafts((prev) => {
        const current = prev[conversationId] ?? "";
        const next = typeof value === "function" ? value(current) : value;
        if (next === current) return prev;
        if (next === "") {
          const copy = { ...prev };
          delete copy[conversationId];
          return copy;
        }
        return { ...prev, [conversationId]: next };
      });
    },
    []
  );

  const setNewMessageBody = useCallback(
    (value: string | ((prev: string) => string)) => {
      if (!selectedConversationId) return;
      updateDraft(selectedConversationId, value);
    },
    [selectedConversationId, updateDraft]
  );

  const handleSelectConversation = (id: string) => {
    setSelectedConversationId(id);
    setSendError(null);
    setSendCooldown(0);
    setLoadMoreError(null);
    setConversations((prev) =>
      prev.map((conv) => (conv.id === id ? { ...conv, unread_count: 0 } : conv))
    );
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (sendCooldown > 0) return;
    const conversationId = selectedConversationId;
    const trimmed = newMessageBody.trim();
    if (!trimmed || !conversationId || !loggedInUser) return;

    const conversation = conversations.find((c) => c.id === conversationId);
    if (!conversation) return;

    updateDraft(conversationId, "");
    setSendError(null);

    try {
      let savedMsg: Message;
      if (conversation.kind === "listing") {
        savedMsg = await messagesApi.send(conversation.rawId, trimmed, loggedInUser.id);
      } else {
        const raw = await friendsApi.sendMessage(conversation.other_participant.public_id, trimmed);
        savedMsg = friendMessageToDisplay(raw, conversation.id);
      }

      setMessages((prev) => {
        const list = prev[selectedConversationId] ?? [];
        // the realtime event may have delivered it first
        if (list.some((m) => String(m.id) === String(savedMsg.id))) return prev;
        return { ...prev, [selectedConversationId]: [...list, savedMsg] };
      });

      setConversations((prev) =>
        prev.map((conv) =>
          conv.id === selectedConversationId
            ? {
              ...conv,
              last_message: savedMsg,
              updated_at: savedMsg.created_at,
            }
            : conv
        )
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        const delay = err.retryAfter && err.retryAfter > 0 ? err.retryAfter : 3;
        setSendCooldown(delay);
        updateDraft(conversationId, (current) => current || trimmed);
        setSendError(
          `Vous envoyez des messages trop rapidement. Veuillez patienter ${delay} seconde${delay > 1 ? "s" : ""} avant de réessayer.`
        );
      } else {
        logError("Erreur lors de l'envoi du message :", err);
        // not sent: give the text back instead of showing a message that does not exist
        updateDraft(conversationId, (current) => current || trimmed);
        setSendError("Le message n'a pas pu être envoyé. Réessayez.");
      }
    }
  };

  const handleMarkAsSold = async (conversationKey: string) => {
    const conversation = conversationsRef.current.find((c) => c.id === conversationKey);
    if (!conversation || conversation.kind !== "listing") return;
    if (conversation.listing_status?.toLowerCase() !== "active") return;
    setIsMarkingSold(true);
    setSendError(null);
    try {
      const updated = await conversationsApi.markAsSold(conversation.rawId);
      setConversations((prev) =>
        prev.map((conv) =>
          conv.id === conversationKey ? { ...conv, ...updated, id: conv.id, kind: conv.kind, rawId: conv.rawId } : conv
        )
      );

      // Add a visual notification message in the chat
      const sysMsg: Message = {
        id: `msg-sys-${Date.now()}`,
        conversation_id: conversationKey,
        sender_id: loggedInUser?.id ?? "system",
        body: `📦 L'annonce a été marquée comme vendue à ${conversation.other_participant.display_name}.`,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => ({
        ...prev,
        [conversationKey]: [...(prev[conversationKey] ?? []), sysMsg],
      }));
    } catch (err) {
      logError("Erreur lors du marquage comme vendu :", err);
      const msg =
        err instanceof Error ? err.message : "Erreur lors du marquage comme vendu";
      setSendError(msg);
      throw err;
    } finally {
      setIsMarkingSold(false);
    }
  };

  const handleReviewSubmitted = (conversationId: string, review: Review) => {
    // Marquer la conversation comme ayant un avis déposé
    setConversations((prev) =>
      prev.map((conv) =>
        String(conv.id) === String(conversationId)
          ? {
            ...conv,
            has_reviewed: true,
          }
          : conv
      )
    );

    // Ajouter un message système dans le chat pour confirmer le dépôt d'avis
    const reviewMsg: Message = {
      id: `msg-rev-${Date.now()}`,
      conversation_id: conversationId,
      sender_id: loggedInUser?.id ?? "system",
      body: `⭐ Avis de ${loggedInUser?.display_name ?? "l'acheteur"} (${review.rating}/5) : « ${review.body} »`,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => ({
      ...prev,
      [conversationId]: [...(prev[conversationId] ?? []), reviewMsg],
    }));
  };

  // "typing"/"friend_typing" goes on our own topic; the server relays it to the other
  const notifyTyping = () => {
    if (!selectedConversationId || !loggedInUser) return;
    const conversation = conversations.find((c) => c.id === selectedConversationId);
    if (!conversation) return;
    const topic = userTopic(loggedInUser.id);
    const id = Number(conversation.rawId);

    const now = Date.now();
    if (now - typingSentAtRef.current > 1500) {
      typingSentAtRef.current = now;
      typingSentRef.current = { kind: conversation.kind, id, topic };
      const payload = conversation.kind === "listing"
        ? { conversation_id: id, is_typing: true }
        : { friend_id: id, is_typing: true };
      sendRealtime(conversation.kind === "listing" ? "typing" : "friend_typing", topic, payload);
    }

    if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);

    typingTimeoutRef.current = setTimeout(stopTyping, 2000);
  };

  // load the previous page of the selected conversation (before_id)
  const handleLoadMore = async () => {
    if (!selectedConversationId || isLoadingMore[selectedConversationId]) return;
    const conversation = conversations.find((c) => c.id === selectedConversationId);
    const current = messages[selectedConversationId] ?? [];
    if (!conversation || current.length === 0) return;

    const oldestId = current[0].id;
    setIsLoadingMore((prev) => ({ ...prev, [selectedConversationId]: true }));
    setLoadMoreError(null);
    try {
      let older: Message[];
      if (conversation.kind === "listing") {
        older = await messagesApi.list(conversation.rawId, oldestId);
      } else {
        const raw = await friendsApi.listMessages(conversation.other_participant.public_id, oldestId);
        older = raw.map((m) => friendMessageToDisplay(m, conversation.id));
      }
      setMessages((prev) => {
        const list = prev[selectedConversationId] ?? [];
        const seen = new Set(list.map((m) => String(m.id)));
        return {
          ...prev,
          [selectedConversationId]: [...older.filter((m) => !seen.has(String(m.id))), ...list],
        };
      });
      setHasMore((prev) => ({ ...prev, [selectedConversationId]: older.length >= MESSAGES_PAGE_SIZE }));
    } catch (err) {
      logError("Erreur lors du chargement des messages précédents :", err);
      setLoadMoreError(
        err instanceof Error
          ? err.message
          : "Erreur lors du chargement des messages plus anciens",
      );
    } finally {
      setIsLoadingMore((prev) => ({ ...prev, [selectedConversationId]: false }));
    }
  };

  const canLoadMore = selectedConversationId ? Boolean(hasMore[selectedConversationId]) : false;
  const loadingMore = selectedConversationId ? Boolean(isLoadingMore[selectedConversationId]) : false;

  return {
    loggedInUser,
    hasMore: canLoadMore,
    isLoadingMore: loadingMore,
    loadMoreError,
    handleLoadMore,
    conversations,
    selectedConversationId,
    setSelectedConversationId,
    isLoading,
    error,
    setError,
    newMessageBody,
    setNewMessageBody,
    sendError,
    sendCooldown,
    activeConversation,
    currentMessages,
    isMarkingSold,
    handleSelectConversation,
    handleSendMessage,
    handleMarkAsSold,
    handleReviewSubmitted,
    isOtherTyping,
    notifyTyping,
  };
}
