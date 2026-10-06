"""Password hashing for email + password accounts.

argon2id with the argon2-cffi defaults (RFC 9106 low-memory profile: 64 MiB,
3 passes). The stored string carries its own salt and parameters, so raising
them later needs no migration.

A hash costs tens of milliseconds of CPU: it runs in a thread, never on the
event loop, which serves every request and socket of the single worker.
"""

import asyncio
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from starlette.concurrency import run_in_threadpool

_hasher = PasswordHasher()

# Each hash holds its 64 MiB while it runs: a burst of logins waits for a slot
# instead of taking all 40 threads of the pool at once (2.5 GiB).
_slots = asyncio.Semaphore(4)

# Checked against when there is no real hash (unknown email, 42-only account),
# so that refusal takes as long as a wrong password.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def _matches(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


async def hash_password(password: str) -> str:
    async with _slots:
        return await run_in_threadpool(_hasher.hash, password)


async def verify_password(password: str, password_hash: str | None) -> bool:
    """False for a wrong password, a malformed hash or no hash at all, after
    the same work in every case: the timing does not tell which emails have
    an account."""
    async with _slots:
        matches = await run_in_threadpool(_matches, password, password_hash or _DUMMY_HASH)
    return matches and password_hash is not None
