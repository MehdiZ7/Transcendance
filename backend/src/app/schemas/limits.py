"""Size limits on what a client can send, in one place.

Nothing here is a security boundary on its own (nginx caps the request body,
quotas cap the row counts), it stops one request from being huge or from
carrying a value the database cannot store. Every limit answers 422 with the
field it refers to.

| Field                                   | Limit                      |
|-----------------------------------------|----------------------------|
| message body (listing chat, friend DM)  | 2000 characters            |
| review body                             | 1000 characters            |
| report reason                           | 1000 characters            |
| bio                                     | 500 characters             |
| display name                            | 50 characters              |
| avatar path                             | 500 characters             |
| listing title                           | 120 characters             |
| listing body                            | 5000 characters            |
| listing price                           | 0 to 10 000 000            |
| listing currency                        | 3 capital letters          |
| images per listing                      | 10, 500 characters each    |
| listing attributes                      | 20 keys, 2 KB of JSON      |
| search text (`q`)                       | 100 characters             |
| page number                             | 1 to 10 000                |
| any database id in a body or a query    | 1 to 2**63 - 1             |
| new password (register, change)         | 8 to 128 characters        |
| password checked (login, current)       | 1 to 128 characters        |
| analytics dates (`startDate`, `endDate`)| 2000-01-01 to 2100-12-31   |

Text fields and searches refuse the NUL character: PostgreSQL cannot store it.
Any other text that reaches the database with one is answered 422 too, by the
handler in main.py.

Text is stripped of leading and trailing whitespace before it is measured, so
a message made of spaces is empty. Passwords are not: a space is part of a
password like any other character. The websocket has its own frame limit
(`ws_max_frame_bytes`).

The values are constants, not settings: changing one changes the contract with
the front (its inputs carry the same `maxLength`), so it is a code change.
"""

import json
from datetime import date
from typing import Annotated, Any

from fastapi import Path, Query
from pydantic import AfterValidator, Field, StringConstraints

MAX_MESSAGE_LENGTH = 2000
MAX_REVIEW_LENGTH = 1000
MAX_REPORT_REASON_LENGTH = 1000
MAX_BIO_LENGTH = 500
MAX_DISPLAY_NAME_LENGTH = 50
MAX_AVATAR_PATH_LENGTH = 500
MAX_LISTING_TITLE_LENGTH = 120
MAX_LISTING_BODY_LENGTH = 5000
MAX_PRICE = 10_000_000
MAX_IMAGES_PER_LISTING = 10
MAX_IMAGE_URL_LENGTH = 500
MAX_ATTRIBUTES_KEYS = 20
MAX_ATTRIBUTES_BYTES = 2048
MAX_SEARCH_LENGTH = 100
MAX_PAGE = 10_000
MAX_TARGET_ID_LENGTH = 64  # a UUID is 36 characters, an int id at most 19
MAX_DB_ID = 2**63 - 1  # BIGINT: anything above is a database error, not a 404
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
MIN_ANALYTICS_DATE = date(2000, 1, 1)  # around year 1 or 9999, date arithmetic overflows
MAX_ANALYTICS_DATE = date(2100, 12, 31)


def _no_nul(value: str | None) -> str | None:
    if value is not None and "\x00" in value:
        raise ValueError("must not contain a NUL character")
    return value


# PostgreSQL refuses a NUL in text: a 422 naming the field, not a database error
NoNul = AfterValidator(_no_nul)


def _text(min_length: int, max_length: int) -> Any:
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length),
        NoNul,
    ]


MessageBody = _text(1, MAX_MESSAGE_LENGTH)
ReviewBody = _text(0, MAX_REVIEW_LENGTH)
ReportReason = _text(1, MAX_REPORT_REASON_LENGTH)
Bio = _text(0, MAX_BIO_LENGTH)
DisplayName = _text(1, MAX_DISPLAY_NAME_LENGTH)
AvatarPath = _text(0, MAX_AVATAR_PATH_LENGTH)
ListingTitle = _text(1, MAX_LISTING_TITLE_LENGTH)
ListingBody = _text(0, MAX_LISTING_BODY_LENGTH)
ImageUrl = _text(1, MAX_IMAGE_URL_LENGTH)
TargetIdText = _text(1, MAX_TARGET_ID_LENGTH)

# Passwords are measured without stripping whitespace: spaces are meaningful.
Password = Annotated[
    str,
    StringConstraints(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH),
]
PasswordInput = Annotated[
    str,
    StringConstraints(min_length=1, max_length=MAX_PASSWORD_LENGTH),
]

DbId = Annotated[int, Field(ge=1, le=MAX_DB_ID)]
Price = Annotated[int, Field(ge=0, le=MAX_PRICE)]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


def _bounded_attributes(value: dict) -> dict:
    if len(value) > MAX_ATTRIBUTES_KEYS:
        raise ValueError(f"at most {MAX_ATTRIBUTES_KEYS} attributes")
    if len(json.dumps(value)) > MAX_ATTRIBUTES_BYTES:
        raise ValueError(f"attributes are limited to {MAX_ATTRIBUTES_BYTES} bytes of JSON")
    return value


Attributes = Annotated[dict, AfterValidator(_bounded_attributes)]

# Route parameters: a path or query id above BIGINT would reach the database as an error
PathId = Annotated[int, Path(ge=1, le=MAX_DB_ID)]
BeforeId = Annotated[int | None, Query(ge=1, le=MAX_DB_ID)]
PageNumber = Annotated[int, Query(ge=1, le=MAX_PAGE)]
AnalyticsDate = Annotated[date, Field(ge=MIN_ANALYTICS_DATE, le=MAX_ANALYTICS_DATE)]
