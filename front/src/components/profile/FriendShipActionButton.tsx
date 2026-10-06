"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import type { FriendshipStatus } from "@/types/user";
import { friendsApi } from "@/lib/api/friends";
import { logError } from "@/lib/log";

interface FriendshipActionButtonProps {
  targetUserId?: string;
  status: FriendshipStatus | null;
  onChange?: (newStatus: FriendshipStatus | null) => void;
  onSendRequest?: () => Promise<void>;
  onRemove?: () => Promise<void>;
  incomingRequestId?: string | null;
  onAccept?: () => Promise<void>;
  onDecline?: () => Promise<void>;
  /** Greys out "Ajouter en ami" (e.g. the API would refuse: they blocked us). */
  disabled?: boolean;
}

export function FriendshipActionButton({
  targetUserId,
  status,
  onChange,
  onSendRequest,
  onRemove,
  incomingRequestId,
  onAccept,
  onDecline,
  disabled = false,
}: FriendshipActionButtonProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAddFriend = async () => {
    if (isLoading || disabled) return;
    setIsLoading(true);
    setError(null);
    try {
      if (onSendRequest) {
        await onSendRequest();
      } else if (targetUserId) {
        await friendsApi.sendRequest(targetUserId);
      }
      onChange?.('pending');
    } catch (err) {
      logError("Erreur lors de l'envoi de la demande d'ami :", err);
      setError(
        err instanceof Error ? err.message : "Erreur lors de l'envoi de la demande d'ami",
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleRemoveFriend = async () => {
    if (isLoading) return;
    setIsLoading(true);
    setError(null);
    try {
      if (onRemove) {
        await onRemove();
      } else if (targetUserId) {
        await friendsApi.remove(targetUserId);
      }
      onChange?.(null);
    } catch (err) {
      logError("Erreur lors du retrait de l'ami :", err);
      setError(
        err instanceof Error ? err.message : "Erreur lors du retrait de l'ami",
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleCancelRequest = async () => {
    if (isLoading) return;
    setIsLoading(true);
    setError(null);
    try {
      if (targetUserId) await friendsApi.cancelRequest(targetUserId);
      onChange?.(null);
    } catch (err) {
      logError("Erreur lors de l'annulation de la demande d'ami :", err);
      setError(
        err instanceof Error
          ? err.message
          : "Erreur lors de l'annulation de la demande d'ami",
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleAccept = async () => {
    if (isLoading) return;
    setIsLoading(true);
    setError(null);
    try {
      if (onAccept) await onAccept();
      else if (incomingRequestId) await friendsApi.accept(incomingRequestId);
      onChange?.('accepted');
    } catch (err) {
      logError("Erreur lors de l'acceptation :", err);
      setError(
        err instanceof Error
          ? err.message
          : "Erreur lors de l'acceptation de la demande d'ami",
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleDecline = async () => {
    if (isLoading) return;
    setIsLoading(true);
    setError(null);
    try {
      if (onDecline) await onDecline();
      else if (incomingRequestId) await friendsApi.decline(incomingRequestId);
    } catch (err) {
      logError("Erreur lors du refus :", err);
      setError(
        err instanceof Error
          ? err.message
          : "Erreur lors du refus de la demande d'ami",
      );
    } finally {
      setIsLoading(false);
    }
  };

  const renderButtons = () => {
    if (status === 'blocked') {
      return (
        <Button type="button" variant="ghost" size="sm" disabled>
          Bloqué
        </Button>
      );
    }

    if (incomingRequestId) {
      return (
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="primary"
            size="sm"
            disabled={isLoading}
            onClick={handleAccept}
          >
            {isLoading ? "…" : "Accepter"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isLoading}
            onClick={handleDecline}
          >
            Refuser
          </Button>
        </div>
      );
    }

    if (status === 'accepted') {
      return (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isLoading}
          onClick={handleRemoveFriend}
        >
          {isLoading ? "Patientez…" : "✓ Amis"}
        </Button>
      );
    }

    if (status === 'pending') {
      return (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={isLoading}
          onClick={handleCancelRequest}
        >
          {isLoading ? "Patientez…" : "Annuler la demande"}
        </Button>
      );
    }

    return (
      <Button
        type="button"
        variant="primary"
        size="sm"
        disabled={isLoading || disabled}
        onClick={handleAddFriend}
      >
        {isLoading ? "Envoi…" : "➕ Ajouter en ami"}
      </Button>
    );
  };

  return (
    <div className="inline-flex flex-col items-start gap-1">
      {renderButtons()}
      {error && (
        <span role="alert" className="text-xs text-rose-600 font-medium">
          {error}
        </span>
      )}
    </div>
  );
}
