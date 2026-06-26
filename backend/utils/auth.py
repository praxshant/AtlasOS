import datetime
import hashlib
import logging
import os
import jwt
from typing import Optional, List, Callable
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.postgres import get_db, User

logger = logging.getLogger(__name__)
settings = get_settings()

# Setup OAuth2 password bearer
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

def hash_password(password: str) -> str:
    """
    Hashes a password using PBKDF2 with a random salt (NIST compliant, zero compilation dependencies).
    """
    salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return f"{salt.hex()}:{hashed.hex()}"

def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verifies a password against the stored PBKDF2 hash.
    """
    try:
        if not hashed_password or ":" not in hashed_password:
            return False
        salt_hex, hashed_hex = hashed_password.split(":")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hashed_hex)
        actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return actual == expected
    except Exception as e:
        logger.error(f"Password verification failed: {e}")
        return False

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    """
    Generates a JWT access token containing the user payload including tenant_id.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def get_current_token(request: Request, header_token: Optional[str] = Depends(oauth2_scheme)) -> str:
    """
    Extracts the token from either the Authorization header or the token query parameter (essential for EventSource/SSE).
    """
    if header_token:
        return header_token
    # Query parameter fallback (for EventSource)
    query_token = request.query_params.get("token")
    if query_token:
        return query_token
        
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Missing authentication token.",
        headers={"WWW-Authenticate": "Bearer"},
    )

def get_current_user(token: str = Depends(get_current_token), db: Session = Depends(get_db)) -> User:
    """
    FastAPI dependency that decodes the JWT token and returns the current User object from the database.
    The user object includes tenant_id for downstream tenant isolation.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
        
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

def get_current_tenant_id(current_user: User = Depends(get_current_user)) -> str:
    """
    FastAPI dependency that extracts the tenant_id from the current authenticated user.
    Used for quick tenant scoping without needing the full user object.
    """
    return current_user.tenant_id

def check_role(allowed_roles: List[str]) -> Callable:
    """
    FastAPI dependency factory that checks if the logged-in user possesses one of the allowed roles.
    """
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource."
            )
        return current_user
    return dependency

def check_tenant_admin() -> Callable:
    """
    FastAPI dependency that ensures the user is a tenant admin (platform-level admin).
    """
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only tenant administrators can perform this action."
            )
        return current_user
    return dependency
