from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

import bcrypt

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    STAFF = "staff"
    OPERATOR = "operator"
    EMPLOYEE = "employee"
    VIEWER = "viewer"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        pw_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pw_bytes, hash_bytes)
    except Exception:
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception:
            return False

def get_password_hash(password: str) -> str:
    try:
        pw_bytes = password.encode("utf-8")[:72]
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")
    except Exception:
        return pwd_context.hash(password[:72])


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    return encoded_jwt

async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> Dict[str, Any]:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        username: Optional[str] = payload.get("sub")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        role: str = str(payload.get("role", Role.VIEWER.value)).lower()
        user_id: Optional[int] = payload.get("user_id")
        person_id: Optional[int] = payload.get("person_id")
        name: str = payload.get("name") or username

        return {
            "id": user_id,
            "user_id": user_id,
            "username": username,
            "name": name,
            "role": role,
            "person_id": person_id
        }
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def require_authenticated_user(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Ensures request is sent by an authenticated user."""
    return current_user

def require_role(required_role: Role):
    async def role_checker(current_user: dict = Depends(get_current_user)):
        roles_hierarchy = {
            Role.VIEWER: 1,
            Role.EMPLOYEE: 2,
            Role.STAFF: 2,
            Role.OPERATOR: 2,
            Role.ADMIN: 3,
            Role.OWNER: 4
        }
        
        user_role_str = str(current_user.get("role", Role.VIEWER.value)).lower()
        try:
            user_level = roles_hierarchy[Role(user_role_str)]
            req_level = roles_hierarchy[required_role]
        except (ValueError, KeyError):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid role")
            
        if user_level < req_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: {required_role.value.upper()} role required"
            )
        return current_user
    return role_checker

async def require_owner(current_user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Strict authorization gate: permits only users whose actual account role is OWNER."""
    user_role = str(current_user.get("role", "")).lower()
    if user_role != Role.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Only users with OWNER role are authorized to perform this operation."
        )
    return current_user

async def log_security_audit(
    db,
    actor_id: Optional[int],
    actor_name: str,
    actor_role: str,
    action: str,
    target_entity: Optional[str] = None,
    details: Optional[str] = None
):
    """Inserts a security audit record into security_audit_logs table."""
    try:
        from app.db.models import SecurityAuditLog
        audit = SecurityAuditLog(
            actor_id=actor_id,
            actor_name=actor_name,
            actor_role=actor_role,
            action=action,
            target_entity=target_entity,
            details=details
        )
        db.add(audit)
        await db.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to write security audit log: {e}")


