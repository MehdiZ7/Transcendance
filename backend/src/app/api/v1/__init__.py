from fastapi import APIRouter

from app.api.v1 import (
    admin_users,
    analytics,
    auth,
    catalog,
	conversations,
    friends,
    health,
    listings,
    reports,
    reviews,
    stats,
    uploads,
    users,
)

router = APIRouter()
router.include_router(admin_users.router, tags=["admin"])
router.include_router(analytics.router, tags=["analytics"])
router.include_router(auth.router, tags=["auth"])
router.include_router(catalog.router, tags=["catalog"])
router.include_router(conversations.router, tags=["conversations"])
router.include_router(friends.router, tags=["friends"])
router.include_router(health.router, tags=["health"])
router.include_router(listings.router, tags=["listings"])
router.include_router(reports.router, tags=["reports"])
router.include_router(reviews.router, tags=["reviews"])
router.include_router(stats.router, tags=["stats"])
router.include_router(uploads.router, tags=["uploads"])
router.include_router(users.router, tags=["users"])
