import uuid

from pydantic import BaseModel, ConfigDict, EmailStr

from app.schemas.limits import DisplayName, Password, PasswordInput


class CurrentUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: uuid.UUID
    display_name: str
    email: str
    role: str
    avatar_path: str | None
    bio: str | None
    # Required, not defaulted: model_validate(user) must fail, not answer False
    # (User has no such attribute, see serializers.to_current_user)
    has_password: bool


class RegisterRequest(BaseModel):
    email: EmailStr
    password: Password
    display_name: DisplayName


class PasswordLoginRequest(BaseModel):
    email: EmailStr
    password: PasswordInput


class ChangePasswordRequest(BaseModel):
    new_password: Password
    current_password: PasswordInput | None = None
