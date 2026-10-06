from pydantic import BaseModel


class PaginatedResponse[T](BaseModel):
    data: list[T]
    total: int
    page: int
    limit: int
    total_pages: int
