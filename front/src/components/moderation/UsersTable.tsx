'use client';

import { useState, useEffect, useCallback, useTransition } from 'react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { Avatar } from '@/components/ui/Avatar';
import { Modal } from '@/components/ui/Modal';
import { usersApi } from '@/lib/api/users';
import type { AdminUser, UserRole } from '@/types/user';

interface UsersTableProps {
  currentUserId?: string;
  onToast?: (message: string) => void;
}

const ROLE_OPTIONS: { value: UserRole; label: string; description: string }[] = [
  { value: 'user', label: 'Utilisateur', description: 'Accès standard à la plateforme' },
  { value: 'moderator', label: 'Modérateur', description: 'Gestion des signalements' },
  { value: 'admin', label: 'Administrateur', description: 'Gestion globale et des utilisateurs' },
];

export function UsersTable({ currentUserId, onToast }: UsersTableProps) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const limit = 15;

  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<string>('all');

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatingUserId, setUpdatingUserId] = useState<string | null>(null);
  const [userToDelete, setUserToDelete] = useState<AdminUser | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const [, startTransition] = useTransition();

  // Fetch users from API (callable manually on actions)
  const fetchUsers = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await usersApi.listUsers({
        page,
        limit,
        q: debouncedSearch.trim() || undefined,
        role: roleFilter !== 'all' ? roleFilter : undefined,
      });
      setUsers(res.data);
      setTotal(res.total);
      setTotalPages(res.total_pages || 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur lors du chargement des utilisateurs');
    } finally {
      setIsLoading(false);
    }
  }, [page, limit, debouncedSearch, roleFilter]);

  // Debounce search query input by 300ms and reset to page 1
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearch(searchQuery);
      setPage(1);
    }, 300);
    return () => clearTimeout(handler);
  }, [searchQuery]);

  // Initial and reactive data fetching
  useEffect(() => {
    let ignore = false;

    usersApi.listUsers({
      page,
      limit,
      q: debouncedSearch.trim() || undefined,
      role: roleFilter !== 'all' ? roleFilter : undefined,
    })
      .then((res) => {
        if (!ignore) {
          setUsers(res.data);
          setTotal(res.total);
          setTotalPages(res.total_pages || 1);
          setError(null);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Erreur lors du chargement des utilisateurs');
          setIsLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [page, limit, debouncedSearch, roleFilter]);

  const handleRoleFilterChange = (newRole: string) => {
    startTransition(() => {
      setRoleFilter(newRole);
      setPage(1);
    });
  };

  // Handle Role Change
  const handleRoleChange = async (user: AdminUser, newRole: UserRole) => {
    if (user.role === newRole) return;
    if (user.public_id === currentUserId) {
      onToast?.('Vous ne pouvez pas modifier votre propre rôle.');
      return;
    }

    setUpdatingUserId(user.public_id);
    try {
      const updated = await usersApi.updateUserRole(user.public_id, newRole);
      setUsers((prev) =>
        prev.map((u) => (u.public_id === user.public_id ? { ...u, role: updated.role } : u))
      );
      const roleLabel = ROLE_OPTIONS.find((r) => r.value === newRole)?.label || newRole;
      onToast?.(`Le rôle de ${user.display_name} a été modifié en ${roleLabel}.`);
    } catch (err) {
      onToast?.(err instanceof Error ? err.message : 'Erreur lors de la modification du rôle.');
    } finally {
      setUpdatingUserId(null);
    }
  };

  // Handle Delete Confirmation
  const handleConfirmDelete = async () => {
    if (!userToDelete) return;
    setIsDeleting(true);
    try {
      await usersApi.deleteUser(userToDelete.public_id);
      onToast?.(`L'utilisateur ${userToDelete.display_name} a été définitivement supprimé.`);
      setUserToDelete(null);
      // Refresh current page
      await fetchUsers();
    } catch (err) {
      onToast?.(err instanceof Error ? err.message : 'Erreur lors de la suppression de l\'utilisateur.');
    } finally {
      setIsDeleting(false);
    }
  };

  // Copy public ID to clipboard
  const handleCopyId = (id: string) => {
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => {
      setCopiedId((prev) => (prev === id ? null : prev));
    }, 2000);
  };

  // Format date helper
  const formatDate = (dateString?: string | null) => {
    if (!dateString) return '—';
    try {
      const d = new Date(dateString);
      return new Intl.DateTimeFormat('fr-FR', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      }).format(d);
    } catch {
      return dateString;
    }
  };

  return (
    <div className="space-y-6">

      {/* Search and Filters Bar */}
      <div className="bg-slate-50 border border-slate-200/80 rounded-2xl p-3 sm:p-4 space-y-3">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          {/* Search Input */}
          <div className="relative flex-1 max-w-md">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Rechercher par nom d'utilisateur..."
              className="w-full pl-9 pr-8 py-2 text-sm rounded-xl border border-slate-200 bg-white text-slate-800 placeholder-slate-400 focus:outline-none focus:border-[#00babc] focus:ring-1 focus:ring-[#00babc] transition-all"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600 transition-colors"
                aria-label="Effacer la recherche"
              >
                ✕
              </button>
            )}
          </div>

          {/* Role Filter Pills */}
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <span className="text-slate-500 font-medium mr-1 hidden lg:inline">Rôle :</span>
            {[
              { id: 'all', label: 'Tous' },
              { id: 'admin', label: 'Admin' },
              { id: 'moderator', label: 'Modérateur' },
              { id: 'user', label: 'Utilisateur' },
            ].map((rf) => (
              <button
                key={rf.id}
                type="button"
                onClick={() => handleRoleFilterChange(rf.id)}
                className={`px-3 py-1.5 rounded-lg font-semibold transition-colors cursor-pointer ${
                  roleFilter === rf.id
                    ? 'bg-slate-900 text-white'
                    : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-100'
                }`}
              >
                {rf.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-sm text-rose-700 flex items-center justify-between">
          <span>{error}</span>
          <Button size="sm" variant="outline" onClick={() => fetchUsers()}>
            Réessayer
          </Button>
        </div>
      )}

      {/* Users Table / Loading / Empty */}
      <Card className="overflow-hidden p-0 border border-slate-200 shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-600">
            <thead className="bg-slate-50 text-xs uppercase font-semibold text-slate-500 border-b border-slate-200 select-none">
              <tr>
                <th scope="col" className="px-5 py-3.5">
                  Utilisateur
                </th>
                <th scope="col" className="px-5 py-3.5 hidden md:table-cell">
                  Date d&apos;inscription
                </th>
                <th scope="col" className="px-5 py-3.5">
                  Statut
                </th>
                <th scope="col" className="px-5 py-3.5">
                  Rôle
                </th>
                <th scope="col" className="px-5 py-3.5 text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {isLoading ? (
                // Skeleton loading rows
                Array.from({ length: 6 }).map((_, idx) => (
                  <tr key={idx} className="animate-pulse">
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full bg-slate-200"></div>
                        <div className="space-y-1.5">
                          <div className="h-4 w-28 bg-slate-200 rounded"></div>
                          <div className="h-3 w-16 bg-slate-100 rounded"></div>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-4 hidden md:table-cell">
                      <div className="h-4 w-20 bg-slate-100 rounded"></div>
                    </td>
                    <td className="px-5 py-4">
                      <div className="h-5 w-16 bg-slate-100 rounded-full"></div>
                    </td>
                    <td className="px-5 py-4">
                      <div className="h-8 w-32 bg-slate-100 rounded-lg"></div>
                    </td>
                    <td className="px-5 py-4 text-right">
                      <div className="h-8 w-8 bg-slate-100 rounded-lg ml-auto"></div>
                    </td>
                  </tr>
                ))
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-5 py-12 text-center text-slate-500">
                    <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto mb-3">
                      <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
                      </svg>
                    </div>
                    <p className="text-sm font-semibold text-slate-800">Aucun utilisateur trouvé</p>
                    <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                      {searchQuery || roleFilter !== 'all'
                        ? 'Essayez de modifier votre recherche ou vos filtres.'
                        : 'Aucun compte enregistré pour le moment.'}
                    </p>
                    {(searchQuery || roleFilter !== 'all') && (
                      <Button
                        size="sm"
                        variant="secondary"
                        className="mt-4"
                        onClick={() => {
                          setSearchQuery('');
                          setRoleFilter('all');
                        }}
                      >
                        Réinitialiser les filtres
                      </Button>
                    )}
                  </td>
                </tr>
              ) : (
                users.map((u) => {
                  const isSelf = u.public_id === currentUserId;
                  const isUpdating = updatingUserId === u.public_id;
                  const isDeleted = Boolean(u.deleted_at);

                  return (
                    <tr
                      key={u.public_id}
                      className={`hover:bg-slate-50/60 transition-colors ${
                        isSelf ? 'bg-amber-50/30' : ''
                      }`}
                    >
                      {/* User Info */}
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <Avatar alt={u.display_name} size="sm" />
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-slate-900">
                                {u.display_name}
                              </span>
                              {isSelf && (
                                <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-200">
                                  Vous
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-1.5 mt-0.5">
                              <span className="font-mono text-xs text-slate-400">
                                {u.public_id.slice(0, 8)}…
                              </span>
                              <button
                                type="button"
                                onClick={() => handleCopyId(u.public_id)}
                                title="Copier l'identifiant complet"
                                className="text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
                                aria-label="Copier l'identifiant"
                              >
                                {copiedId === u.public_id ? (
                                  <svg className="w-3.5 h-3.5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                                  </svg>
                                ) : (
                                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
                                  </svg>
                                )}
                              </button>
                            </div>
                          </div>
                        </div>
                      </td>

                      {/* Created At */}
                      <td className="px-5 py-4 hidden md:table-cell text-xs text-slate-500 whitespace-nowrap">
                        {formatDate(u.created_at)}
                      </td>

                      {/* Status */}
                      <td className="px-5 py-4 whitespace-nowrap">
                        {isDeleted ? (
                          <Badge variant="closed">Supprimé</Badge>
                        ) : !u.is_active ? (
                          <Badge variant="warning">Suspendu</Badge>
                        ) : (
                          <Badge variant="success">Actif</Badge>
                        )}
                      </td>

                      {/* Role Selector */}
                      <td className="px-5 py-4 whitespace-nowrap">
                        <div className="flex items-center gap-2">
                          <div className="relative">
                            <select
                              value={u.role}
                              disabled={isSelf || isDeleted || isUpdating}
                              onChange={(e) => handleRoleChange(u, e.target.value as UserRole)}
                              title={
                                isSelf
                                  ? 'Vous ne pouvez pas modifier votre propre rôle'
                                  : isDeleted
                                  ? 'Ce compte est supprimé'
                                  : 'Changer le rôle de cet utilisateur'
                              }
                              className={`appearance-none text-xs font-semibold rounded-lg pl-2.5 pr-7 py-1.5 border transition-all cursor-pointer disabled:cursor-not-allowed disabled:opacity-60 ${
                                u.role === 'admin'
                                  ? 'bg-purple-50 text-purple-900 border-purple-200 hover:border-purple-300'
                                  : u.role === 'moderator'
                                  ? 'bg-blue-50 text-blue-900 border-blue-200 hover:border-blue-300'
                                  : 'bg-slate-50 text-slate-800 border-slate-200 hover:border-slate-300'
                              } focus:outline-none focus:ring-1 focus:ring-[#00babc]`}
                            >
                              {ROLE_OPTIONS.map((opt) => (
                                <option key={opt.value} value={opt.value}>
                                  {opt.label}
                                </option>
                              ))}
                            </select>
                            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-1.5 text-slate-400">
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                              </svg>
                            </div>
                          </div>

                          {isUpdating && (
                            <svg className="animate-spin h-3.5 w-3.5 text-[#00babc]" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                            </svg>
                          )}
                        </div>
                      </td>

                      {/* Action buttons */}
                      <td className="px-5 py-4 text-right whitespace-nowrap">
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={isSelf || isUpdating}
                          onClick={() => setUserToDelete(u)}
                          title={isSelf ? 'Vous ne pouvez pas vous supprimer vous-même' : 'Supprimer définitivement cet utilisateur'}
                          className="text-slate-400 hover:text-rose-600 hover:bg-rose-50 p-1.5 rounded-lg"
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                          </svg>
                        </Button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination bar */}
        {!isLoading && total > 0 && (
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 px-5 py-3.5 border-t border-slate-200 bg-slate-50/50">
            <span className="text-xs text-slate-500">
              Affichage de <span className="font-semibold text-slate-900">{Math.min((page - 1) * limit + 1, total)}</span> à{' '}
              <span className="font-semibold text-slate-900">{Math.min(page * limit, total)}</span> sur{' '}
              <span className="font-semibold text-slate-900">{total}</span> {total <= 1 ? 'utilisateur' : 'utilisateurs'}
            </span>

            {totalPages > 1 && (
              <div className="flex items-center gap-1.5 text-xs">
                <button
                  type="button"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 font-medium hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Précédent
                </button>

                {Array.from({ length: totalPages }).map((_, i) => {
                  const pageNum = i + 1;
                  // Only show near pages if many pages
                  if (
                    pageNum === 1 ||
                    pageNum === totalPages ||
                    (pageNum >= page - 1 && pageNum <= page + 1)
                  ) {
                    return (
                      <button
                        key={pageNum}
                        type="button"
                        onClick={() => setPage(pageNum)}
                        className={`w-8 h-8 rounded-lg font-semibold transition-colors ${
                          page === pageNum
                            ? 'bg-[#00babc] text-slate-950 font-bold'
                            : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100'
                        }`}
                      >
                        {pageNum}
                      </button>
                    );
                  }
                  if (pageNum === page - 2 || pageNum === page + 2) {
                    return (
                      <span key={pageNum} className="px-1 text-slate-400 select-none">
                        …
                      </span>
                    );
                  }
                  return null;
                })}

                <button
                  type="button"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 font-medium hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Suivant
                </button>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Delete User Confirmation Modal */}
      <Modal
        isOpen={Boolean(userToDelete)}
        onClose={() => {
          if (!isDeleting) setUserToDelete(null);
        }}
        title="Supprimer un utilisateur"
      >
        {userToDelete && (
          <div className="space-y-4 text-sm text-slate-700">
            <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs">
              <strong>Attention :</strong> Cette action est <strong>irréversible</strong>. La suppression supprimera immédiatement la ligne en base de données et effectuera une suppression en cascade de toutes ses annonces, conversations, messages, avis et favoris.
            </div>

            <p>
              Êtes-vous sûr de vouloir supprimer définitivement le compte de{' '}
              <span className="font-bold text-slate-900">{userToDelete.display_name}</span> (ID: <code className="text-xs bg-slate-100 px-1 py-0.5 rounded font-mono">{userToDelete.public_id}</code>) ?
            </p>

            <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
              <Button
                variant="outline"
                disabled={isDeleting}
                onClick={() => setUserToDelete(null)}
              >
                Annuler
              </Button>
              <Button
                variant="danger"
                isLoading={isDeleting}
                onClick={handleConfirmDelete}
              >
                Supprimer définitivement
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
