import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.limits import DbId, ReviewBody
from app.schemas.user import PublicUser


class ReviewRead(BaseModel):
    id: int
    conversation_id: int
    rating: int
    body: str | None
    created_at: datetime
    author: PublicUser


class ReviewCreate(BaseModel):
    conversation_id: DbId
    subject_id: uuid.UUID
    rating: int = Field(ge=1, le=5)
    body: ReviewBody | None = None


class ReviewCreated(BaseModel):
    id: int
    conversation_id: int
    author_id: uuid.UUID
    subject_id: uuid.UUID
    rating: int
    body: str | None
    created_at: datetime
