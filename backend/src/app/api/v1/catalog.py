from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import get_session
from app.models import Category, Location
from app.schemas.catalog import CategoryWithAttributes, LocationRead

router = APIRouter()


@router.get("/categories")
async def list_categories(
    session: AsyncSession = Depends(get_session),
) -> list[CategoryWithAttributes]:
    result = await session.execute(
        select(Category).options(selectinload(Category.attributes)).order_by(Category.depth, Category.category_name)
    )
    categories = result.scalars().all()
    return [CategoryWithAttributes.model_validate(category) for category in categories]


@router.get("/locations")
async def list_locations(
    session: AsyncSession = Depends(get_session),
) -> list[LocationRead]:
    result = await session.execute(select(Location).order_by(Location.location))
    locations = result.scalars().all()
    return [LocationRead.model_validate(location) for location in locations]
