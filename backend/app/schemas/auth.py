import uuid

from pydantic import BaseModel, EmailStr

from app.models.user import Role


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: EmailStr
    full_name: str
    role: Role
    is_active: bool

    model_config = {"from_attributes": True}
