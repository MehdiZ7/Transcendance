from pydantic import BaseModel, ConfigDict


class CategoryAttributeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    data_type: str
    unit: str | None
    is_required: bool
    is_filterable: bool
    options: dict | list | None


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    depth: int
    category_name: str
    is_leaf: bool


class CategoryWithAttributes(CategoryRead):
    attributes: list[CategoryAttributeRead]


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    location: str
