"use client";

import { MAX_BIO_LENGTH, MAX_DISPLAY_NAME_LENGTH } from "@/lib/limits";
import { Heading } from "@/components/ui/Heading";
import { Card } from "@/components/ui/Card";
import { Badge, BadgeVariant } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import ListingCard from "@/components/listings/ListingCard";
import { AvatarUploadDropzone } from "@/components/ui/AvatarUploadDropzone";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ReportButton } from "@/components/ui/ReportModal";
import { FriendshipActionButton } from "@/components/profile/FriendShipActionButton";
import { usePresence } from "@/hooks/usePresence";
import { useProfile, PROFILE_PAGE_SIZE } from "@/hooks/useProfile";
import { Pagination } from "@/components/ui/Pagination";
import { DeleteReviewButton } from "@/components/reviews/DeleteReviewButton";
import { UserStatsDashboard } from "@/components/profile/UserStatsDashboard";
import { PasswordForm } from "@/components/profile/PasswordForm";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { useAuthModal } from "@/context/AuthModalContext";
import { useCurrentUser } from "@/hooks/useCurrentUser";

function getRoleVariant(role: string): BadgeVariant {
  if (role === 'admin') return 'admin';
  if (role === 'moderator') return 'moderator';
  return 'default';
}

// onClick wiring for async handlers: the error is already surfaced via
// actionError, so swallow the rethrow instead of leaving it unhandled.
function run(fn: () => Promise<void>) {
  return () => {
    void fn().catch(() => {});
  };
}

export interface ProfilPageProps {
  profileId?: string;
}

function ProfileContent({ profileId }: ProfilPageProps) {
  const { openAuthModal } = useAuthModal();
  const { user: currentUser } = useCurrentUser();
  // state (effect) for the online user
  const { isOnline } = usePresence();

  const {
    userData,
    isLoading,
    error,
    isOwnProfile,
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
    isCancelModalOpen,
    setIsCancelModalOpen,
    isFriendsModalOpen,
    setIsFriendsModalOpen,
    friendToRemove,
    setFriendToRemove,
    activeTab,
    setActiveTab,
    friendshipStatus,
    setFriendshipStatus,
    handleCancelEdit,
    handleSubmit,
    handleAttemptCancel,
    handleConfirmRemoveFriend,
    incomingRequest,
    handleAcceptRequest,
    handleDeclineRequest,
    pendingRequests,
    handleDeleteReview,
    isBlocked,
    handleToggleBlock,
    handleRemoveFriendDirect,
    actionError,
    setActionError,
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
  } = useProfile(profileId);

  if (isLoading) {
    return (
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-sm text-gray-500">
        Chargement…
      </main>
    );
  }

  if (error) {
    return (
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-sm text-rose-600">
        {error}
      </main>
    );
  }

  if (!userData) {
    return null;
  }

  return (
    <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-10 pb-12">
      <div className="space-y-6">
        {actionError && (
          <div
            role="alert"
            className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-sm text-rose-700 font-medium flex items-center justify-between shadow-xs"
          >
            <span>{actionError}</span>
            <button
              type="button"
              onClick={() => setActionError(null)}
              className="text-rose-500 hover:text-rose-800 text-sm font-bold ml-2 cursor-pointer"
            >
              ✕
            </button>
          </div>
        )}
        <Card className="p-6">
          <div className="flex flex-col sm:flex-row items-start gap-6">
            <Avatar
              src={userData.avatar_path}
              alt={userData.display_name}
              size="xl"
            />

            <div className="flex-1 min-w-0 space-y-4">
              <div>
                {/* Header : name + badge role*/}
                <div className="flex items-center justify-between w-full">
                  <div className="flex items-center gap-3">
                    <Heading level={2}>{userData.display_name}</Heading>
                    <Badge variant={getRoleVariant(userData.role)}>
                      {userData.role}
                    </Badge>
                  </div>

                  {!isOwnProfile && (
                    <ReportButton
                      targetType="user"
                      targetId={userData.public_id}
                      targetTitle={userData.display_name}
                      variant="link"
                      label="Signaler cet utilisateur"
                    />
                  )}
                </div>
                {userData.created_at && (
                  <p className="text-xs text-gray-500 mt-1">
                    Membre depuis le{" "}
                    {new Date(userData.created_at).toLocaleDateString('fr-FR', {
                      day: 'numeric',
                      month: 'long',
                      year: 'numeric',
                    })}
                  </p>
                )}
                {/* Rating badge*/}
                <div className="mt-2">
                  <Badge variant="default" className="text-sm px-3 py-1 font-semibold">
                    {userData.rating > 0 ? `${userData.rating.toFixed(1)} ★` : "Nouveau"}
                  </Badge>
                </div>
              </div>

              {/* information  */}
              <div>
                <Heading level={3} className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">
                  À propos
                </Heading>
                <p className={`text-sm ${userData.bio ? "text-gray-700 leading-relaxed" : "text-gray-400 italic"}`}>
                  {userData.bio ?? "Aucune biographie renseignée."}
                </p>
              </div>

              {/* Friends button */}
              <div className="flex items-center justify-between pt-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setActionError(null);
                    setIsFriendsModalOpen(true);
                  }}
                >
                  🌐 {userData.friends_count ?? 0} {(userData.friends_count ?? 0) > 1 ? "amis" : "ami"}
                </Button>

                {isOwnProfile ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setDisplayName(userData.display_name);
                      setBio(userData.bio ?? '');
                      setAvatarPath(userData.avatar_path ?? '');
                      setIsEditOpen(true);
                    }}
                  >
                    Éditer le profil
                  </Button>
                ) : (
                  <div className="flex items-center gap-2">
                    {/* direct messages are friends-only, there is no conversation to open otherwise */}
                    {friendshipStatus === 'accepted' && (
                      <Link
                        href={`/messages?user=${userData.public_id}`}
                        onClick={(e) => {
                          if (!currentUser) {
                            e.preventDefault();
                            openAuthModal();
                          }
                        }}
                      >
                        <Button type="button" variant="outline" size="sm">
                          💬 Message
                        </Button>
                      </Link>
                    )}
                    {/* They blocked us: the API would refuse our request, so the button
                        is greyed out. Our own block still shows "Bloqué" whatever they did. */}
                    <FriendshipActionButton
                      targetUserId={userData.public_id || userData.id}
                      status={isBlocked ? 'blocked' : friendshipStatus}
                      disabled={Boolean(userData.has_blocked_me)}
                      incomingRequestId={incomingRequest?.id ?? null}
                      onChange={setFriendshipStatus}
                      onRemove={handleRemoveFriendDirect}
                      onAccept={async () => {
                        if (incomingRequest) await handleAcceptRequest(incomingRequest);
                      }}
                      onDecline={async () => {
                        if (incomingRequest) await handleDeclineRequest(incomingRequest);
                      }}
                    />
                    <Button
                      type="button"
                      variant={isBlocked ? "outline" : "ghost"}
                      size="sm"
                      className={isBlocked ? "" : "text-red-600 hover:text-red-700 hover:bg-red-50"}
                      onClick={run(handleToggleBlock)}
                    >
                      {isBlocked ? "Débloquer" : "Bloquer"}
                    </Button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </Card>

        {/* Navigation tab : By changing the activetab state */}
        <div className="border-b border-gray-200">
          <nav
            className={
              isOwnProfile
                ? "grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-4 pb-2 px-2 sm:px-6"
                : "grid grid-cols-3 gap-4 pb-2 px-6"
            }
          >
            <Button
              type="button"
              variant={activeTab === 'listings' ? 'secondary' : "ghost"}
              size="md"
              onClick={() => setActiveTab('listings')}
              fullWidth
            >
              Annonces ({userData.listings_count ?? 0})
            </Button>
            <Button
              type="button"
              variant={activeTab === 'likes' ? "secondary" : "ghost"}
              size="md"
              onClick={() => setActiveTab("likes")}
              fullWidth
            >
              Favoris ({userData.liked_listings_count ?? 0})
            </Button>
            <Button
              type="button"
              variant={activeTab === 'reviews' ? "secondary" : "ghost"}
              size="md"
              onClick={() => setActiveTab('reviews')}
              fullWidth
            >
              Avis ({userData.reviews?.length ?? userData.reviews_count ?? userData.rating_count ?? 0})
            </Button>
            {isOwnProfile && (
              <Button
                type="button"
                variant={activeTab === 'stats' ? "secondary" : "ghost"}
                size="md"
                onClick={() => setActiveTab('stats')}
                fullWidth
              >
                 Statistiques
              </Button>
            )}
          </nav>
        </div>

        {/* listing tab */}
        {activeTab === 'listings' && (
          !userData.recent_listings || userData.recent_listings.length === 0 ? (
            <EmptyState
              title="Aucune annonce publiée"
              description="Aucun objet n'a été mis en location pour le moment."
              action={
                isOwnProfile ? (
                  <Button href="/listings/create" size="sm" variant="primary">
                    Créer une annonce
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                {userData.recent_listings.map((listing) => (
                  <ListingCard key={listing.id} data={listing} />
                ))}
              </div>
              {listingsTotalPages > 1 && (
                <Pagination
                  currentPage={listingsPage}
                  totalPages={listingsTotalPages}
                  totalResults={listingsTotal}
                  limit={PROFILE_PAGE_SIZE}
                  onPageChange={goToListingsPage}
                  isLoading={isLoadingListings}
                />
              )}
            </>
          )
        )}

        {/*  liked tab */}
        {activeTab === 'likes' && (
          !userData.liked_listings || userData.liked_listings.length === 0 ? (
            <EmptyState
              title="Aucune annonce favorite"
              description="Aucune annonce enregistrée dans les favoris."
              action={
                <Button href="/" size="sm" variant="outline">
                  Parcourir les annonces
                </Button>
              }
            />
          ) : (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                {userData.liked_listings.map((listing) => (
                  <ListingCard key={listing.id} data={listing} />
                ))}
              </div>
              {favoritesTotalPages > 1 && (
                <Pagination
                  currentPage={favoritesPage}
                  totalPages={favoritesTotalPages}
                  totalResults={favoritesTotal}
                  limit={PROFILE_PAGE_SIZE}
                  onPageChange={goToFavoritesPage}
                  isLoading={isLoadingFavorites}
                />
              )}
            </>
          )
        )}

        {/* review tabs */}
        {activeTab === 'reviews' && (
          !userData.reviews || userData.reviews.length === 0 ? (
            <EmptyState
              title="Aucun avis pour le moment"
              description="Aucune évaluation ni commentaire reçus pour le moment."
            />
          ) : (
            <div className="space-y-4">
              {userData.reviews.map((review) => (
                <Card key={review.id} className="p-4">
                  <div className="flex items-start gap-4">
                    <Avatar
                      src={review.author?.avatar_path ?? undefined}
                      alt={review.author?.display_name ?? "Auteur inconnu"}
                      size="md"
                    />
                    <div className="flex-1 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-sm text-gray-900">
                          {review.author?.display_name ?? "Auteur inconnu"}
                        </span>
                        <div className="flex items-center gap-3">
                          <span className="text-xs text-gray-400">
                            {new Date(review.created_at).toLocaleDateString('fr-FR', {
                              day: 'numeric',
                              month: 'short',
                              year: 'numeric',
                            })}
                          </span>
                          {review.author_id !== currentUser?.id &&
                            review.author?.public_id !== currentUser?.public_id && (
                              <ReportButton
                                targetType="review"
                                targetId={review.id}
                                targetTitle={review.author?.display_name}
                                variant="link"
                                label="Signaler cet avis"
                              />
                            )}
                          <DeleteReviewButton
                            reviewId={review.id}
                            authorId={review.author_id}
                            authorPublicId={review.author?.public_id}
                            onDelete={handleDeleteReview}
                          />
                        </div>
                      </div>
                      <div className="flex items-center text-amber-500 text-sm">
                        {'★'.repeat(review.rating)}
                        <span className="text-gray-300">
                          {'★'.repeat(5 - review.rating)}
                        </span>
                      </div>
                      <p className="text-sm text-gray-700 pt-1 leading-relaxed">
                        {review.body}
                      </p>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )
        )}

        {/* stats tab */}
        {activeTab === 'stats' && isOwnProfile && (
          <UserStatsDashboard
            stats={userStats}
            isLoading={isStatsLoading}
            error={statsError}
            onRetry={refetchStats}
          />
        )}
      </div>

      {/* Modal : editing profil */}
      {isOwnProfile && (
        <>
          <Modal
            isOpen={isEditOpen}
            onClose={handleAttemptCancel}
            title="Éditer le profil"
          >
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* update of the avatar */}
              <div className="flex flex-col items-center pb-2 gap-2">
                <label className="block text-sm font-medium text-gray-700">
                  Photo de profil
                </label>
                <AvatarUploadDropzone
                  defaultValue={avatarPath}
                  onChange={(newAvatar: string | null) => setAvatarPath(newAvatar ?? "")}
                  onUploadingChange={setIsUploadingAvatar}
                />
                {avatarPath ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="text-xs text-red-600 hover:text-red-700 hover:bg-red-50"
                    onClick={() => setAvatarPath("")}
                  >
                    🗑️ Supprimer la photo
                  </Button>
                ) : null}
              </div>

              {/* Name div */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Nom de profil
                </label>
                <input
                  type="text"
                  value={displayName}
                  maxLength={MAX_DISPLAY_NAME_LENGTH}
                  onChange={(e) => setDisplayName(e.target.value)}
                  className="w-full p-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              {/* Information div */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Biographie
                </label>
                <textarea
                  value={bio}
                  maxLength={MAX_BIO_LENGTH}
                  onChange={(e) => setBio(e.target.value)}
                  rows={3}
                  className="w-full p-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
                />
              </div>

              {editError && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
                  {editError}
                </div>
              )}

              {/* action button*/}
              <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-gray-100">
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleAttemptCancel}
                  disabled={isSaving}
                >
                  Annuler
                </Button>
                <Button
                  type="submit"
                  isLoading={isSaving}
                  disabled={isSaving || isUploadingAvatar}
                >
                  Enregistrer
                </Button>
              </div>
            </form>

            <PasswordForm hasPassword={Boolean(userData.has_password)} />
          </Modal>

          {/* Modal : are you sure ? after exit a modification */}
          <Modal
            isOpen={isCancelModalOpen}
            onClose={() => setIsCancelModalOpen(false)}
            title="Abandonner les modifications ?"
          >
            <div className="space-y-4 pt-1">
              <p className="text-sm text-gray-600 leading-relaxed">
                Êtes-vous sûr de vouloir annuler ? Toutes les modifications non enregistrées seront perdues.
              </p>
              <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-100">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsCancelModalOpen(false)}
                >
                  Continuer la saisie
                </Button>
                <Button
                  type="button"
                  variant="danger"
                  onClick={handleCancelEdit}
                >
                  Oui, abandonner
                </Button>
              </div>
            </div>
          </Modal>
        </>
      )}

      {/* Modal : friends listing*/}
      <Modal
        isOpen={isFriendsModalOpen}
        onClose={() => setIsFriendsModalOpen(false)}
        title={`Liste des amis (${userData.friends_count ?? 0})`}
      >
        <div className="space-y-4 pt-1">
          {actionError && (
            <p role="alert" className="text-xs text-rose-600 font-medium bg-rose-50 p-2.5 rounded-lg border border-rose-200">
              {actionError}
            </p>
          )}
          {isOwnProfile && pendingRequests.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Demandes d&apos;ami ({pendingRequests.length})
              </p>
              {pendingRequests.map((request) => (
                <div
                  key={request.id}
                  className="flex items-center justify-between p-2 rounded-lg bg-amber-50/60 border border-amber-200/70 gap-2"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <Avatar
                      src={request.requester?.avatar_path ?? undefined}
                      alt={request.requester?.display_name ?? "Utilisateur"}
                      size="sm"
                    />
                    <p className="text-sm font-semibold text-gray-900 truncate">
                      {request.requester?.display_name ?? "Utilisateur"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      type="button"
                      variant="primary"
                      size="sm"
                      onClick={run(() => handleAcceptRequest(request))}
                    >
                      Accepter
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={run(() => handleDeclineRequest(request))}
                    >
                      Refuser
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
          {!userData.friends || userData.friends.length === 0 ? (
            <p className="text-sm text-gray-500 italic py-4 text-center">
              Aucun ami dans la liste.
            </p>
          ) : (
            <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
              {userData.friends.map((friend) => (
                <div
                  key={friend.id}
                  className="flex items-center justify-between p-2 rounded-lg hover:bg-gray-50 transition-colors gap-2"
                >
                  <Link
                    href={`/profile/${friend.public_id}`}
                    className="flex items-center gap-3 group min-w-0 flex-1"
                  >
                    <Avatar
                      src={friend.avatar_path ?? undefined}
                      alt={friend.display_name}
                      size="sm"
                    />
                    <div className="truncate">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-semibold text-gray-900 group-hover:text-purple-600 transition-colors truncate">
                          {friend.display_name}
                        </p>
                        <Badge variant={getRoleVariant(friend.role)}>
                          {friend.role}
                        </Badge>
                        {isOnline(friend.id) ? (
                          <span className="shrink-0 text-[10px] font-semibold text-emerald-600">
                            ● En ligne
                          </span>
                        ) : (
                          <span className="shrink-0 text-[10px] font-semibold text-rose-500">
                            ● Hors ligne
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-400">
                        {friend.rating > 0 ? `${friend.rating.toFixed(1)} ★` : "Nouveau"}
                      </p>
                    </div>
                  </Link>

                  <div className="flex items-center gap-1 shrink-0">
                    <Link
                      href={`/messages?user=${friend.public_id}`}
                      onClick={(e) => {
                        if (!currentUser) {
                          e.preventDefault();
                          openAuthModal();
                        }
                      }}
                    >
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        title="Envoyer un message"
                      >
                        💬
                      </Button>
                    </Link>
                    {isOwnProfile && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-red-600 hover:text-red-700 hover:bg-red-50"
                        onClick={() => {
                          setActionError(null);
                          setFriendToRemove(friend);
                        }}
                        title="Retirer de la liste d'amis"
                      >
                        ✕
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-center justify-end pt-4 border-t border-gray-100">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsFriendsModalOpen(false)}
            >
              Fermer
            </Button>
          </div>
        </div>
      </Modal>

      {/* Modal "are you sure" after a delete friend */}
      {isOwnProfile && (
        <Modal
          isOpen={!!friendToRemove}
          onClose={() => setFriendToRemove(null)}
          title="Retirer un ami ?"
        >
          <div className="space-y-4 pt-1">
            {actionError && (
              <p role="alert" className="text-xs text-rose-600 font-medium bg-rose-50 p-2.5 rounded-lg border border-rose-200">
                {actionError}
              </p>
            )}
            <p className="text-sm text-gray-600 leading-relaxed">
              Êtes-vous sûr de vouloir retirer{" "}
              <span className="font-semibold text-gray-900">
                {friendToRemove?.display_name}
              </span>{" "}
              de votre liste d&apos;amis ?
            </p>
            <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-100">
              <Button
                type="button"
                variant="outline"
                onClick={() => setFriendToRemove(null)}
              >
                Annuler
              </Button>
              <Button
                type="button"
                variant="danger"
                onClick={handleConfirmRemoveFriend}
              >
                Oui, retirer
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </main>
  );
}

export default function ProfilPage({ profileId: propProfileId }: ProfilPageProps = {}) {
  const params = useParams();
  const routeProfileId = typeof params?.public_id === 'string' ? params.public_id : undefined;
  const profileId = propProfileId || routeProfileId;

  if (!profileId) {
    return (
      <AuthGuard>
        <ProfileContent />
      </AuthGuard>
    );
  }

  return <ProfileContent profileId={profileId} />;
}

