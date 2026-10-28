from datetime import datetime, timedelta, timezone
import bcrypt
import base64
import hashlib
import hmac
import secrets
from jose import jwt
from config import settings


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > 4096:
        raise ValueError("Password is too long")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(encoded, salt=salt, n=16384, r=8, p=1, dklen=64, maxmem=64*1024*1024)
    return "scrypt$16384$8$1$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(derived).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        encoded = plain_password.encode("utf-8")
        if len(encoded) > 4096:
            return False
        if hashed_password.startswith("scrypt$"):
            algorithm, n, r, p, salt, expected = hashed_password.split("$")
            # Stored hashes cannot request arbitrary CPU/memory costs.
            if (n,r,p) != ("16384","8","1"):
                return False
            salt = base64.urlsafe_b64decode(salt)
            expected = base64.urlsafe_b64decode(expected)
            if len(salt)!=16 or len(expected)!=64:
                return False
            actual = hashlib.scrypt(encoded, salt=salt, n=16384, r=8, p=1, dklen=64, maxmem=64*1024*1024)
            return hmac.compare_digest(actual, expected)
        # Existing bcrypt accounts remain valid; never silently truncate a supplied password.
        if hashed_password.startswith(("$2a$","$2b$","$2y$")) and len(encoded)<=72:
            return bcrypt.checkpw(encoded, hashed_password.encode("utf-8"))
        return False
    except (ValueError, TypeError, AttributeError):
        return False


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.setdefault("exp", expire)
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.JWTError:
        return None
