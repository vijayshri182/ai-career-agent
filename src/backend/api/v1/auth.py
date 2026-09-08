"""Auth router."""


from fastapi import APIRouter, Depends, status

from backend.api.deps import (
    get_auth_service,
    get_current_user,
    handle_domain_error,
)
from backend.core.security_service import get_security_service as security_svc
from backend.models.user import User
from backend.schemas.auth import Token, UserLogin, UserRead, UserRegister
from backend.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegister, auth_service: AuthService = Depends(get_auth_service)
):
    try:
        user = await auth_service.register(data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    token = security_svc().create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login", response_model=Token)
async def login(
    data: UserLogin, auth_service: AuthService = Depends(get_auth_service)
):
    try:
        user = await auth_service.authenticate(data)
    except Exception as exc:
        raise handle_domain_error(exc) from exc
    token = security_svc().create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)):
    return current_user
