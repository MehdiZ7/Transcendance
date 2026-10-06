from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.core.serializers import to_current_user
from app.models import User
from app.schemas.auth import CurrentUser

router = APIRouter()


@router.get("/auth/me")
async def me(user: User = Depends(get_current_user)) -> CurrentUser:
    return to_current_user(user)
