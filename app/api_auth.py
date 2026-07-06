from fastapi import APIRouter, HTTPException, status

from app import repository
from app.auth import create_token, hash_password, verify_password
from app.db import get_pool
from app.models import TokenResponse, UserLogin, UserRegister

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: UserRegister):
    pool = get_pool()
    existing = await repository.get_user_by_email(pool, data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    hashed = hash_password(data.password)
    user_id = await repository.create_user(pool, data.email, hashed)
    return TokenResponse(access_token=create_token(user_id))


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin):
    pool = get_pool()
    user = await repository.get_user_by_email(pool, data.email)
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return TokenResponse(access_token=create_token(user["id"]))
