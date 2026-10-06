"use client";

import { useState, useEffect } from "react";
import type { PublicUser, FriendshipStatus, UserProfile, Friend, MyStats } from "@/types";
import type { Review } from "@/types/report";
import { usersApi } from "@/lib/api/users";
import { friendsApi } from "@/lib/api/friends";
import { reviewsApi } from "@/lib/api/reviews";
import { listingsApi } from "@/lib/api/listings";
import { logError } from "@/lib/log";
import type { Listing } from "@/types/listing";
import type { PaginatedResponse } from "@/types";

export type ProfileTab = 'listings' | 'likes' | 'reviews' | 'stats';

export const PROFILE_PAGE_SIZE = 12;

function emptyListingPage(): PaginatedResponse<Listing> {
  return { data: [], total: 0, page: 1, limit: PROFILE_PAGE_SIZE, total_pages: 0 };
}

export function useProfile(profileId?: string) {
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [userData, setUserData] = useState<UserProfile | null>(null);
  const [isOwnProfile, setIsOwnProfile] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // user stats state
  const [userStats, setUserStats] = useState<MyStats | null>(null);
  const [isStatsLoading, setIsStatsLoading] = useState(false);
  const [statsError, setStatsError] = useState<string | null>(null);

  // editing profile state
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [bio, setBio] = useState("");
  const [avatarPath, setAvatarPath] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // modals state
  const [isCancelModalOpen, setIsCancelModalOpen] = useState(false);
  const [isFriendsModalOpen, setIsFriendsModalOpen] = useState(false);
  const [friendToRemove, setFriendToRemove] = useState<PublicUser | null>(null);
  const [activeTab, setActiveTab] = useState<ProfileTab>('listings');

  // friends state
  const [friendshipStatus, setFriendshipStatus] = useState<FriendshipStatus | null>(null);
  const [pendingRequests, setPendingRequests] = useState<Friend[]>([]);
  const [isBlocked, setIsBlocked] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // pagination state
  const [listingsPage, setListingsPage] = useState(1);
  const [listingsTotal, setListingsTotal] = useState(0);
  const [listingsTotalPages, setListingsTotalPages] = useState(0);
  const [isLoadingListings, setIsLoadingListings] = useState(false);
  const [favoritesPage, setFavoritesPage] = useState(1);
  const [favoritesTotal, setFavoritesTotal] = useState(0);
  const [favoritesTotalPages, setFavoritesTotalPages] = useState(0);
  const [isLoadingFavorites, setIsLoadingFavorites] = useState(false);

  useEffect(() => {
    let isMounted = true;

    usersApi.getCurrent()
      .then(async (me) => {
        if (!isMounted) return;
        if (!me) {
          setError("Vous devez être connecté pour voir ce profil.");
          return;
        }
        setCurrentUser(me);

        const isOwn = !profileId || profileId === me.id || profileId === me.public_id;
        setIsOwnProfile(isOwn);

        const targetRef = isOwn ? (me.public_id || me.id) : profileId;
        const targetPromise = isOwn ? Promise.resolve(me) : usersApi.getByRef(profileId);
        const [
          resolvedTarget,
          resolvedReviews,
          resolvedListings,
          resolvedFavorites,
          resolvedFriends,
          resolvedPending,
          resolvedBlocked,
        ] = await Promise.all([
          targetPromise,
          reviewsApi.listByUser(targetRef).catch(() => [] as Review[]),
          listingsApi
            .getByUser(targetRef, { page: 1, limit: PROFILE_PAGE_SIZE })
            .catch(() => emptyListingPage()),
          listingsApi
            .getFavoritesByUser(targetRef, { page: 1, limit: PROFILE_PAGE_SIZE })
            .catch(() => emptyListingPage()),
          friendsApi.list(targetRef).catch(() => [] as PublicUser[]),
          friendsApi.listPending(me.public_id || me.id).catch(() => [] as Friend[]),
          usersApi.getBlocked().catch(() => [] as PublicUser[]),
        ]);


        if (!isMounted) return;
        if (!resolvedTarget) {
          setError("Utilisateur introuvable");
          return;
        }

        const isUserBlocked = resolvedBlocked.some(
          (u) => u.id === resolvedTarget.id || u.public_id === resolvedTarget.public_id
        );
        setIsBlocked(isUserBlocked);
        const profile = resolvedTarget as unknown as Partial<UserProfile>;

        const reviewsList = resolvedReviews;
        const listingsList = resolvedListings.data;
        const favoritesList = resolvedFavorites.data;
        const friendsList = resolvedFriends;

        setPendingRequests(resolvedPending);

        setListingsPage(resolvedListings.page);
        setListingsTotal(resolvedListings.total);
        setListingsTotalPages(resolvedListings.total_pages);
        setFavoritesPage(resolvedFavorites.page);
        setFavoritesTotal(resolvedFavorites.total);
        setFavoritesTotalPages(resolvedFavorites.total_pages);

        setUserData({
          ...resolvedTarget,
          recent_listings: listingsList,
          liked_listings: favoritesList,
          friends: friendsList,
          reviews: reviewsList,
          listings_count: resolvedListings.total,
          liked_listings_count: resolvedFavorites.total,
          friends_count: friendsList.length || (profile.friends_count ?? 0),
          reviews_count: reviewsList.length || (profile.reviews_count ?? 0),
        });

        if (isOwn) {
          setFriendshipStatus(null);
        } else if (isUserBlocked) {
          setFriendshipStatus('blocked');
        } else {
          // we are already friends if iam in the friendslist
          const isAlreadyFriend = friendsList.some(
            (friend) => friend.id === me.id || friend.public_id === me.public_id
          );
          setFriendshipStatus(isAlreadyFriend ? 'accepted' : null);
        }

        if (isOwn) {
          setIsStatsLoading(true);
          usersApi.getMyStats()
            .then((stats) => {
              if (!isMounted) return;
              setUserStats(stats);
            })
            .catch((err) => {
              if (!isMounted) return;
              setStatsError(err instanceof Error ? err.message : 'Impossible de charger vos statistiques');
            })
            .finally(() => {
              if (isMounted) setIsStatsLoading(false);
            });
        }
      })
      .catch((err: unknown) => {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : 'Impossible de charger le profil');
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [profileId]);

  const handleCancelEdit = () => {
    setDisplayName(userData?.display_name ?? '');
    setBio(userData?.bio ?? '');
    setAvatarPath(userData?.avatar_path ?? '');
    setEditError(null);
    setIsCancelModalOpen(false);
    setIsEditOpen(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedName = displayName.trim();
    if (!trimmedName) {
      setEditError("Le nom de profil ne peut pas être vide.");
      return;
    }

    setIsSaving(true);
    setEditError(null);
    try {
      const updated = await usersApi.update({
        display_name: trimmedName,
        bio: bio.trim() || null,
        avatar_path: avatarPath || null,
      });

      const newDisplayName = updated.display_name ?? trimmedName;
      const newBio = updated.bio !== undefined ? (updated.bio ?? "") : bio;
      const newAvatarPath = updated.avatar_path !== undefined ? (updated.avatar_path ?? "") : avatarPath;

      setDisplayName(newDisplayName);
      setBio(newBio);
      setAvatarPath(newAvatarPath);

      setUserData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          display_name: newDisplayName,
          bio: newBio,
          avatar_path: newAvatarPath,
        };
      });

      setCurrentUser((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          display_name: newDisplayName,
          bio: newBio,
          avatar_path: newAvatarPath,
        };
      });

      setIsEditOpen(false);
    } catch (err: unknown) {
      logError("Erreur lors de la mise à jour du profil :", err);
      setEditError(err instanceof Error ? err.message : "Erreur lors de la sauvegarde du profil");
    } finally {
      setIsSaving(false);
    }
  };

  const handleAttemptCancel = () => {
    const hasChanges =
      displayName !== (userData?.display_name ?? '') ||
      bio !== (userData?.bio ?? '') ||
      avatarPath !== (userData?.avatar_path ?? '');

    if (hasChanges) {
      setIsCancelModalOpen(true);
    } else {
      setEditError(null);
      setIsEditOpen(false);
    }
  };

  const handleToggleBlock = async () => {
    if (!userData) return;
    const ref = userData.public_id || userData.id;
    setActionError(null);
    try {
      if (isBlocked) {
        await usersApi.unblock(ref);
        setIsBlocked(false);
        setFriendshipStatus(null);
      } else {
        await usersApi.block(ref);
        setIsBlocked(true);
        // the API deleted the friendship with the block: nothing left to show but
        // "Bloqué", which the page derives from isBlocked
        setFriendshipStatus(null);
        setPendingRequests((prev) =>
          prev.filter(
            (r) =>
              r.requester_id !== userData.id &&
              r.requester_id !== userData.public_id &&
              r.requester?.id !== userData.id &&
              r.requester?.public_id !== userData.public_id
          )
        );
        setUserData((prev) => {
          if (!prev) return prev;
          const wasFriend = prev.friends?.some(
            (f) =>
              (currentUser?.id && f.id === currentUser.id) ||
              (currentUser?.public_id && f.public_id === currentUser.public_id)
          );
          if (!wasFriend) return prev;
          const updatedFriends = prev.friends?.filter(
            (f) =>
              (!currentUser?.id || f.id !== currentUser.id) &&
              (!currentUser?.public_id || f.public_id !== currentUser.public_id)
          ) ?? [];
          return {
            ...prev,
            friends: updatedFriends,
            friends_count: Math.max(0, (prev.friends_count ?? 1) - 1),
          };
        });
      }
    } catch (err) {
      logError("Erreur lors du blocage/déblocage :", err);
      setActionError(
        err instanceof Error ? err.message : "Erreur lors du blocage/déblocage",
      );
      throw err;
    }
  };

  const handleRemoveFriendDirect = async () => {
    if (!userData) return;
    const ref = userData.public_id || userData.id;
    setActionError(null);
    try {
      await friendsApi.remove(ref);
      setFriendshipStatus(null);
      setUserData((prev) => {
        if (!prev) return prev;
        const updatedFriends = prev.friends?.filter(
          (f) =>
            (!currentUser?.id || f.id !== currentUser.id) &&
            (!currentUser?.public_id || f.public_id !== currentUser.public_id)
        ) ?? [];
        return {
          ...prev,
          friends: updatedFriends,
          friends_count: Math.max(0, (prev.friends_count ?? 1) - 1),
        };
      });
    } catch (err) {
      logError("Erreur lors de la suppression de l'ami :", err);
      setActionError(
        err instanceof Error ? err.message : "Erreur lors de la suppression de l'ami",
      );
      throw err;
    }
  };

  const handleConfirmRemoveFriend = async () => {
    if (!friendToRemove) return;
    setActionError(null);
    try {
      await friendsApi.remove(friendToRemove.public_id || friendToRemove.id);

      setUserData((prev) => {
        if (!prev) return prev;
        const updatedFriends = prev.friends?.filter(
          (friend) => friend.id !== friendToRemove.id && friend.public_id !== friendToRemove.public_id
        ) ?? [];
        return {
          ...prev,
          friends: updatedFriends,
          friends_count: updatedFriends.length,
        };
      });

      setCurrentUser((prev) => {
        if (!prev) return prev;
        const updatedFriends = prev.friends?.filter(
          (friend) => friend.id !== friendToRemove.id && friend.public_id !== friendToRemove.public_id
        ) ?? [];
        return {
          ...prev,
          friends: updatedFriends,
          friends_count: updatedFriends.length,
        };
      });
    } catch (err) {
      logError("Erreur lors de la suppression de l'ami :", err);
      setActionError(
        err instanceof Error ? err.message : "Erreur lors de la suppression de l'ami",
      );
    } finally {
      setFriendToRemove(null);
    }
  };

  const handleDeleteReview = async (reviewId: string) => {
    setActionError(null);
    try {
      await reviewsApi.delete(reviewId);
      setUserData((prev) => {
        if (!prev) return prev;
        const updated = (prev.reviews ?? []).filter((r) => r.id !== reviewId);
        return { ...prev, reviews: updated, reviews_count: updated.length };
      });
    } catch (err) {
      logError("Erreur lors de la suppression de l'avis :", err);
      setActionError(
        err instanceof Error ? err.message : "Erreur lors de la suppression de l'avis",
      );
    }
  };

  //here we check if the target has sent us a friend request
  const incomingRequest = !isOwnProfile && userData
    ? (pendingRequests.find(
      (r) =>
        r.requester_id === userData.id ||
        r.requester?.id === userData.id ||
        r.requester?.public_id === userData.public_id
    ) ?? null)
    : null;

  const handleAcceptRequest = async (request: Friend) => {
    setActionError(null);
    try {
      await friendsApi.accept(request.id);
      setPendingRequests((prev) => prev.filter((r) => r.id !== request.id));

      // we accept the friend request
      const newFriend = request.requester;
      if (newFriend) {
        setUserData((prev) => {
          if (!prev) return prev;
          const updatedFriends = [...(prev.friends ?? []), newFriend];
          return { ...prev, friends: updatedFriends, friends_count: updatedFriends.length };
        });
      }
      setFriendshipStatus('accepted');
    } catch (err) {
      logError("Erreur lors de l'acceptation de la demande :", err);
      setActionError(
        err instanceof Error ? err.message : "Erreur lors de l'acceptation de la demande",
      );
      throw err;
    }
  };

  const handleDeclineRequest = async (request: Friend) => {
    setActionError(null);
    try {
      await friendsApi.decline(request.id);
      setPendingRequests((prev) => prev.filter((r) => r.id !== request.id));
    } catch (err) {
      logError("Erreur lors du refus de la demande :", err);
      setActionError(
        err instanceof Error ? err.message : "Erreur lors du refus de la demande",
      );
      throw err;
    }
  };

  const refetchStats = async () => {
    if (!isOwnProfile) return;
    setIsStatsLoading(true);
    setStatsError(null);
    try {
      const stats = await usersApi.getMyStats();
      setUserStats(stats);
    } catch (err) {
      setStatsError(err instanceof Error ? err.message : 'Impossible de charger vos statistiques');
    } finally {
      setIsStatsLoading(false);
    }
  };

  const goToListingsPage = async (page: number) => {
    const ref = userData?.public_id || userData?.id;
    if (!ref || isLoadingListings) return;
    setIsLoadingListings(true);
    setActionError(null);
    try {
      const res = await listingsApi.getByUser(ref, { page, limit: PROFILE_PAGE_SIZE });
      setUserData((prev) =>
        prev ? { ...prev, recent_listings: res.data, listings_count: res.total } : prev
      );
      setListingsPage(res.page);
      setListingsTotal(res.total);
      setListingsTotalPages(res.total_pages);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      logError("Erreur lors du chargement des annonces :", err);
      setActionError("Impossible de charger cette page d'annonces.");
      // the banner is at the top of the page, the pagination at the bottom
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } finally {
      setIsLoadingListings(false);
    }
  };

  const goToFavoritesPage = async (page: number) => {
    const ref = userData?.public_id || userData?.id;
    if (!ref || isLoadingFavorites) return;
    setIsLoadingFavorites(true);
    setActionError(null);
    try {
      const res = await listingsApi.getFavoritesByUser(ref, { page, limit: PROFILE_PAGE_SIZE });
      setUserData((prev) =>
        prev ? { ...prev, liked_listings: res.data, liked_listings_count: res.total } : prev
      );
      setFavoritesPage(res.page);
      setFavoritesTotal(res.total);
      setFavoritesTotalPages(res.total_pages);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      logError("Erreur lors du chargement des favoris :", err);
      setActionError("Impossible de charger cette page de favoris.");
      // the banner is at the top of the page, the pagination at the bottom
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } finally {
      setIsLoadingFavorites(false);
    }
  };

  return {
    currentUser,
    userData,
    isOwnProfile,
    isLoading,
    error,
    userStats,
    isStatsLoading,
    statsError,
    refetchStats,
    isEditOpen,
    setIsEditOpen,
    displayName,
    setDisplayName,
    bio,
    setBio,
    avatarPath,
    setAvatarPath,
    isSaving,
    isUploadingAvatar,
    setIsUploadingAvatar,
    editError,
    setEditError,
    actionError,
    setActionError,
    isCancelModalOpen,
    setIsCancelModalOpen,
    isFriendsModalOpen,
    setIsFriendsModalOpen,
    pendingRequests,
    friendToRemove,
    setFriendToRemove,
    activeTab,
    setActiveTab,
    friendshipStatus,
    incomingRequest,
    handleAcceptRequest,
    handleDeclineRequest,
    setFriendshipStatus,
    handleCancelEdit,
    handleSubmit,
    handleAttemptCancel,
    handleConfirmRemoveFriend,
    handleDeleteReview,
    isBlocked,
    handleToggleBlock,
    handleRemoveFriendDirect,
    listingsPage,
    listingsTotal,
    listingsTotalPages,
    isLoadingListings,
    goToListingsPage,
    favoritesPage,
    favoritesTotal,
    favoritesTotalPages,
    isLoadingFavorites,
    goToFavoritesPage,
  };
}
