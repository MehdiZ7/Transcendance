"use client";

import React from "react";
import Link from "next/link";
import { useCurrentUser } from "@/hooks/useCurrentUser";
import { useAuthModal } from "@/context/AuthModalContext";

interface SellerProfileLinkProps {
  sellerPublicId: string;
  sellerId?: string | number | null;
  isOwner?: boolean;
}

export function SellerProfileLink({
  sellerPublicId,
  sellerId,
  isOwner: isOwnerProp,
}: SellerProfileLinkProps) {
  const { user } = useCurrentUser();
  const { openAuthModal } = useAuthModal();

  const isOwner =
    isOwnerProp !== undefined
      ? isOwnerProp
      : !!user &&
        ((sellerId != null && String(user.id) === String(sellerId)) ||
          (sellerPublicId != null && String(user.public_id) === String(sellerPublicId)));

  const handleClick = (e: React.MouseEvent) => {
    if (!user) {
      e.preventDefault();
      openAuthModal();
    }
  };

  return (
    <Link
      href={isOwner ? "/profile" : `/profile/${sellerPublicId}`}
      onClick={handleClick}
      className="inline-flex items-center justify-between w-full text-xs font-semibold text-slate-700 hover:text-[#00babc] transition-colors"
    >
      <span>{isOwner ? "Consulter mon profil" : "Consulter le profil étudiant"}</span>
      <span>→</span>
    </Link>
  );
}
