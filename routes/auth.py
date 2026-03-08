import hashlib
import hmac
import os
from base64 import b64decode, b64encode

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db import get_db_connection

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    gmail: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=6, max_length=200)


class LoginRequest(BaseModel):
    gmail: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=6, max_length=200)


def _password_pepper() -> str:
    return os.getenv("AUTH_PASSWORD_PEPPER", "samplify-default-pepper")


def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        200_000,
    )
    return f"{b64encode(salt).decode()}${b64encode(key).decode()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_b64, key_b64 = stored_hash.split("$", 1)
        salt = b64decode(salt_b64.encode())
        expected_key = b64decode(key_b64.encode())
    except Exception:
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        200_000,
    )
    return hmac.compare_digest(candidate, expected_key)


def _normalize_gmail(gmail: str) -> str:
    value = gmail.strip().lower()
    if not value.endswith("@gmail.com"):
        raise HTTPException(status_code=400, detail="gmail must be a valid @gmail.com address")
    return value


@router.post("/signup")
def signup(request: SignupRequest):
    gmail = _normalize_gmail(request.gmail)
    password_hash = _hash_password(f"{request.password}{_password_pepper()}")

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Failed to connect to database")

    try:
        with conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE gmail = %s", (gmail,))
                if cursor.fetchone():
                    raise HTTPException(status_code=409, detail="Account already exists for this gmail")

                cursor.execute(
                    """
                    INSERT INTO users (name, gmail, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id, name, gmail
                    """,
                    (request.name.strip(), gmail, password_hash),
                )
                user_id, name, user_gmail = cursor.fetchone()
    finally:
        conn.close()

    return {
        "message": "Signup successful",
        "user": {"id": user_id, "name": name, "gmail": user_gmail},
    }


@router.post("/login")
def login(request: LoginRequest):
    gmail = _normalize_gmail(request.gmail)
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Failed to connect to database")

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, gmail, password_hash FROM users WHERE gmail = %s",
                (gmail,),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=401, detail="Invalid gmail or password")

            user_id, name, user_gmail, password_hash = row
            ok = _verify_password(f"{request.password}{_password_pepper()}", password_hash)
            if not ok:
                raise HTTPException(status_code=401, detail="Invalid gmail or password")
    finally:
        conn.close()

    return {
        "message": "Login successful",
        "user": {"id": user_id, "name": name, "gmail": user_gmail},
    }
