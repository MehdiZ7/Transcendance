import os
import uuid

os.environ.setdefault("POSTGRES_DB", "lebon42_test")
os.environ.setdefault("FT_CLIENT_ID", "test-uid")
os.environ.setdefault("FT_CLIENT_SECRET", "test-secret")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.config import settings
from app.core.db import engine, get_session
from app.core.oauth42 import FtProfile, OAuthLoginError, get_ft_client
from app.core.security import create_session_token
from app.main import app
from app.models import (
    Category,
    Conversation,
    Friend,
    Listing,
    ListingFavorite,
    ListingImage,
    Location,
    Message,
    Report,
    Review,
    User,
)


@pytest_asyncio.fixture
async def db_session():
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        yield session
        await session.close()
        await trans.rollback()


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
def create_user(db_session):
    async def _create(**kwargs) -> User:
        defaults = {
            "email": f"user-{uuid.uuid4()}@42.fr",
            "display_name": "Test User",
            "password_hash": "x",
        }
        defaults.update(kwargs)
        user = User(**defaults)
        db_session.add(user)
        await db_session.flush()
        return user

    return _create


@pytest_asyncio.fixture
def create_category(db_session):
    async def _create(**kwargs) -> Category:
        defaults = {"category_name": f"Category {uuid.uuid4()}", "depth": 0, "is_leaf": True}
        defaults.update(kwargs)
        category = Category(**defaults)
        db_session.add(category)
        await db_session.flush()
        return category

    return _create


@pytest_asyncio.fixture
def create_location(db_session):
    async def _create(**kwargs) -> Location:
        defaults = {"location": f"Location {uuid.uuid4()}"}
        defaults.update(kwargs)
        location = Location(**defaults)
        db_session.add(location)
        await db_session.flush()
        return location

    return _create


@pytest_asyncio.fixture
def create_listing(db_session, create_user):
    async def _create(**kwargs) -> Listing:
        if "seller_id" not in kwargs:
            seller = await create_user()
            kwargs["seller_id"] = seller.id
        defaults = {"title": "Test listing", "price": 1000, "status": "active"}
        defaults.update(kwargs)
        listing = Listing(**defaults)
        db_session.add(listing)
        await db_session.flush()
        return listing

    return _create


@pytest_asyncio.fixture
def create_listing_image(db_session, create_listing):
    async def _create(**kwargs) -> ListingImage:
        if "listing_id" not in kwargs:
            listing = await create_listing()
            kwargs["listing_id"] = listing.id
        defaults = {"storage_path": "/mock/listings/default.jpg", "position": 0}
        defaults.update(kwargs)
        image = ListingImage(**defaults)
        db_session.add(image)
        await db_session.flush()
        return image

    return _create


@pytest_asyncio.fixture
def create_listing_favorite(db_session, create_listing, create_user):
    async def _create(**kwargs) -> ListingFavorite:
        if "listing_id" not in kwargs:
            listing = await create_listing()
            kwargs["listing_id"] = listing.id
        if "user_id" not in kwargs:
            user = await create_user()
            kwargs["user_id"] = user.id
        favorite = ListingFavorite(**kwargs)
        db_session.add(favorite)
        await db_session.flush()
        return favorite

    return _create


@pytest_asyncio.fixture
def create_conversation(db_session, create_listing, create_user):
    async def _create(**kwargs) -> Conversation:
        if "listing_id" not in kwargs:
            listing = await create_listing()
            kwargs["listing_id"] = listing.id
            kwargs.setdefault("seller_id", listing.seller_id)
        if "seller_id" not in kwargs:
            listing = await db_session.get_one(Listing, kwargs["listing_id"])
            kwargs["seller_id"] = listing.seller_id
        if "buyer_id" not in kwargs:
            buyer = await create_user()
            kwargs["buyer_id"] = buyer.id
        conversation = Conversation(**kwargs)
        db_session.add(conversation)
        await db_session.flush()
        return conversation

    return _create


@pytest_asyncio.fixture
def create_message(db_session, create_conversation, create_user):
    async def _create(**kwargs) -> Message:
        if "conversation_id" not in kwargs:
            conversation = await create_conversation()
            kwargs["conversation_id"] = conversation.id
        if "sender_id" not in kwargs:
            sender = await create_user()
            kwargs["sender_id"] = sender.id
        defaults = {"body": "Test message"}
        defaults.update(kwargs)
        message = Message(**defaults)
        db_session.add(message)
        await db_session.flush()
        return message

    return _create


@pytest_asyncio.fixture
def create_review(db_session, create_user, create_conversation):
    async def _create(**kwargs) -> Review:
        if "conversation_id" not in kwargs:
            conversation = await create_conversation()
            kwargs["conversation_id"] = conversation.id
        if "author_id" not in kwargs:
            author = await create_user()
            kwargs["author_id"] = author.id
        if "subject_id" not in kwargs:
            subject = await create_user()
            kwargs["subject_id"] = subject.id
        defaults = {"rating": 5}
        defaults.update(kwargs)
        review = Review(**defaults)
        db_session.add(review)
        await db_session.flush()
        return review

    return _create


@pytest_asyncio.fixture
def create_friend(db_session, create_user):
    async def _create(**kwargs) -> Friend:
        if "requester_id" not in kwargs:
            requester = await create_user()
            kwargs["requester_id"] = requester.id
        if "address_id" not in kwargs:
            address = await create_user()
            kwargs["address_id"] = address.id
        defaults = {"status": "pending"}
        defaults.update(kwargs)
        friend = Friend(**defaults)
        db_session.add(friend)
        await db_session.flush()
        return friend

    return _create


@pytest_asyncio.fixture
def create_report(db_session, create_user, create_listing):
    async def _create(**kwargs) -> Report:
        if "reporter_id" not in kwargs:
            reporter = await create_user()
            kwargs["reporter_id"] = reporter.id
        if "target_id" not in kwargs:
            listing = await create_listing()
            kwargs["target_id"] = listing.id
        defaults = {"target_type": "listing", "reason": "Test reason"}
        defaults.update(kwargs)
        report = Report(**defaults)
        db_session.add(report)
        await db_session.flush()
        return report

    return _create


@pytest_asyncio.fixture
def listing_payload(create_category, create_location):
    async def _build(**overrides):
        category, location = await create_category(), await create_location()
        payload = {
            "title": "Clavier",
            "body": "TKL",
            "price": 6500,
            "category_id": category.id,
            "location_id": location.id,
        }
        return {**payload, **overrides}

    return _build


@pytest.fixture(autouse=True)
def _fresh_rate_limiter():
    """The counters live in the process: one test's requests must not count
    against the next one's."""
    ratelimit.limiter.clear()


class FakeFtOAuthClient:
    """Stands in for the intra: no network, and each test can reshape the
    profile it hands back to simulate a rename, a new avatar, ..."""

    def __init__(self) -> None:
        self.profile = FtProfile(
            id=42042, login="jdoe", email="jdoe@student.42.fr", avatar_url=None
        )
        self.exchanged_codes: list[str] = []
        self.fail_with: OAuthLoginError | None = None

    def authorize_url(self, state: str) -> str:
        return f"https://intra.example/authorize?state={state}"

    async def exchange_code(self, code: str) -> str:
        self.exchanged_codes.append(code)
        if self.fail_with is not None:
            raise self.fail_with
        return "intra-access-token"

    async def fetch_profile(self, access_token: str) -> FtProfile:
        return self.profile


@pytest_asyncio.fixture
def fake_ft():
    client = FakeFtOAuthClient()
    app.dependency_overrides[get_ft_client] = lambda: client
    yield client
    app.dependency_overrides.pop(get_ft_client, None)


@pytest_asyncio.fixture
def login_as(client):
    """Attach a valid session cookie for an existing user to the test client."""

    def _login(user: User) -> None:
        client.cookies.set(
            settings.session_cookie_name, create_session_token(user.public_id)
        )

    return _login
