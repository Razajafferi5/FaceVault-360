"""Authentication and user management routes."""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict

from app.core.security import (
    create_access_token,
    verify_password,
    get_password_hash,
    get_current_user,
    require_role,
    require_owner,
    log_security_audit,
    Role
)
from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import SystemUser

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class UserCreate(BaseModel):
    username: str
    password: str
    role: Role = Role.OPERATOR


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str
    role: Optional[str] = None
    is_owner: Optional[bool] = None
    user: Optional[Dict[str, Any]] = None


class LoginJsonRequest(BaseModel):
    username: str
    password: str


class SignupRequest(BaseModel):
    full_name: Optional[str] = None
    username: Optional[str] = None
    username_or_email: Optional[str] = None
    email: Optional[str] = None
    password: str
    confirm_password: Optional[str] = None


@router.post("/signup", response_model=Token)
async def signup(data: SignupRequest, db: AsyncSession = Depends(get_db)):
    """
    Owner and User Sign Up Endpoint:
    - If NO Owner account exists in system, assigns OWNER role (initial Owner setup).
    - If an Owner already exists, public signup assigns OPERATOR (Staff) role.
    - Prevents unauthorized privilege escalation to Owner.
    - Hashes password using bcrypt.
    """
    from app.db.models import Person, SystemUser
    from sqlalchemy import func

    # 1. Validation
    if len(data.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters long."
        )
    if data.confirm_password is not None and data.password != data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match."
        )

    raw_uname = data.username or data.username_or_email or data.email or "user"
    uname = raw_uname.strip()
    full_name = (data.full_name or uname).strip()
    # 2. Check if already exists in system_users
    existing = await db.execute(
        select(SystemUser).where(
            (func.lower(SystemUser.username) == uname.lower()) |
            (func.lower(SystemUser.email) == uname.lower())
        )
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this username or email already exists."
        )

    # 3. Determine Role:
    # Only the first registered user or if no owner exists gets OWNER role.
    owner_sys = await db.execute(select(SystemUser).where(func.lower(SystemUser.role) == "owner"))
    owner_person = await db.execute(select(Person).where(func.lower(Person.role) == "owner"))
    has_owner = bool(owner_sys.scalars().first() or owner_person.scalars().first())

    if not has_owner:
        assigned_role = Role.OWNER.value
    else:
        assigned_role = Role.OPERATOR.value

    hashed_pw = get_password_hash(data.password)
    new_user = SystemUser(
        username=uname,
        email=uname if "@" in uname else None,
        full_name=data.full_name.strip(),
        hashed_password=hashed_pw,
        role=assigned_role,
        is_active=True
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    user_display_name = new_user.full_name or new_user.username
    is_owner = (assigned_role == Role.OWNER.value)

    token = create_access_token(data={
        "sub": new_user.username,
        "role": assigned_role,
        "user_id": new_user.id,
        "name": user_display_name
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": assigned_role,
        "is_owner": is_owner,
        "user": {
            "id": new_user.id,
            "username": new_user.username,
            "name": user_display_name,
            "role": assigned_role,
            "is_owner": is_owner
        }
    }


@router.post("/login-json", response_model=Token)
async def login_json(
    credentials: LoginJsonRequest,
    db: AsyncSession = Depends(get_db)
):
    """JSON-based Login endpoint for animated frontend UI."""
    from app.db.models import Person, SystemUser
    from sqlalchemy import func

    settings = get_settings()
    uname = credentials.username.strip()

    # Query system user by username or email
    result = await db.execute(
        select(SystemUser).where(
            (func.lower(SystemUser.username) == uname.lower()) |
            (func.lower(SystemUser.email) == uname.lower())
        )
    )
    user = result.scalars().first()

    # Auto-seed default admin/owner if no users exist
    if not user and uname == settings.ADMIN_USERNAME:
        all_users = (await db.execute(select(SystemUser))).scalars().all()
        if not all_users:
            default_admin = SystemUser(
                username=settings.ADMIN_USERNAME,
                full_name="Syed Raza Abbas",
                hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
                role=Role.OWNER.value,
                is_active=True
            )
            db.add(default_admin)
            await db.commit()
            await db.refresh(default_admin)
            user = default_admin

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Authoritative SystemUser role is single source of truth
    role_str = user.role.value if isinstance(user.role, Role) else str(user.role)
    role_str = role_str.lower()
    display_name = user.full_name or user.username
    person_id = user.person_id

    # If person_id is not set, attempt exact match with Person table
    if not person_id:
        res_p = await db.execute(select(Person).where(Person.name == user.username))
        p = res_p.scalars().first()
        if p:
            person_id = p.id
            user.person_id = p.id
            await db.commit()

    is_owner = (role_str == Role.OWNER.value)
    access_token = create_access_token(data={
        "sub": user.username,
        "role": role_str,
        "user_id": user.id,
        "id": user.id,
        "person_id": person_id,
        "name": display_name
    })

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": role_str,
        "is_owner": is_owner,
        "user": {
            "id": user.id,
            "username": user.username,
            "name": display_name,
            "email": user.email,
            "role": role_str,
            "person_id": person_id,
            "is_owner": is_owner
        }
    }


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    settings = get_settings()
    from app.db.models import Person, SystemUser
    from sqlalchemy import func

    result = await db.execute(
        select(SystemUser).where(
            (func.lower(SystemUser.username) == form_data.username.lower()) |
            (func.lower(SystemUser.email) == form_data.username.lower())
        )
    )
    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role_str = user.role.value if isinstance(user.role, Role) else str(user.role)
    role_str = role_str.lower()
    display_name = user.full_name or user.username
    person_id = user.person_id

    if not person_id:
        res_p = await db.execute(select(Person).where(Person.name == user.username))
        p = res_p.scalars().first()
        if p:
            person_id = p.id
            user.person_id = p.id
            await db.commit()

    is_owner = (role_str == Role.OWNER.value)

    access_token = create_access_token(data={
        "sub": user.username,
        "role": role_str,
        "user_id": user.id,
        "id": user.id,
        "person_id": person_id,
        "name": display_name
    })
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": role_str,
        "is_owner": is_owner,
        "user": {
            "id": user.id,
            "username": user.username,
            "name": display_name,
            "email": user.email,
            "role": role_str,
            "person_id": person_id,
            "is_owner": is_owner
        }
    }



@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """Invalidate authenticated session acknowledgment."""
    return {"success": True, "message": "Successfully logged out"}


class SwitchUserRequest(BaseModel):
    person_id: Optional[int] = None
    username: Optional[str] = None
    role: Optional[str] = None


@router.get("/me")
async def get_me(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns current authenticated user details.
    SystemUser is the single source of truth for name, email, and role.
    NEVER overwrites with another employee's profile.
    """
    from app.db.models import Person, SystemUser
    from sqlalchemy import func

    user_id = current_user.get("user_id") or current_user.get("id")
    username = current_user.get("username") or current_user.get("sub")

    user = None
    if user_id:
        res = await db.execute(select(SystemUser).where(SystemUser.id == user_id))
        user = res.scalars().first()
    if not user and username:
        res = await db.execute(select(SystemUser).where(func.lower(SystemUser.username) == username.lower()))
        user = res.scalars().first()

    if user:
        role_str = user.role.value if isinstance(user.role, Role) else str(user.role).lower()
        display_name = user.full_name or user.username
        email = user.email
        person_id = user.person_id
        is_owner = (role_str == Role.OWNER.value)

        # Linked person data for staff attendance lookup
        person_details = None
        if person_id:
            p_res = await db.execute(select(Person).where(Person.id == person_id))
            p = p_res.scalars().first()
            if p:
                person_details = {
                    "person_id": p.id,
                    "person_identifier": p.person_identifier,
                    "department": p.department,
                    "face_registered": (p.status == "active")
                }

        return {
            "id": user.id,
            "username": user.username,
            "name": display_name,
            "email": email,
            "role": role_str,
            "is_owner": is_owner,
            "person_id": person_id,
            "person_details": person_details
        }

    # Fallback to token claims if DB record not found
    role = str(current_user.get("role", "viewer")).lower()
    uname = username or "user"
    return {
        "id": user_id or 1,
        "username": uname,
        "name": current_user.get("name", uname),
        "email": None,
        "role": role,
        "is_owner": (role == Role.OWNER.value),
        "person_id": current_user.get("person_id"),
        "person_details": None
    }


@router.get("/users-list")
async def get_users_list(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Returns system accounts and registered persons with their roles."""
    from app.db.models import Person, SystemUser

    users_res = await db.execute(select(SystemUser).order_by(SystemUser.id))
    system_users = users_res.scalars().all()

    items = []
    for u in system_users:
        items.append({
            "id": u.id,
            "type": "system",
            "name": u.full_name or u.username,
            "username": u.username,
            "email": u.email,
            "role": u.role.lower() if hasattr(u.role, "lower") else str(u.role).lower(),
            "person_id": u.person_id,
            "is_owner": (str(u.role).lower() == "owner")
        })

    return {"success": True, "users": items}


class ChangeOwnerRequest(BaseModel):
    target_user_id: Optional[int] = None
    target_username: Optional[str] = None
    new_role_for_previous_owner: Optional[str] = "admin"


@router.post("/change-owner")
async def change_owner(
    req: ChangeOwnerRequest,
    current_user: dict = Depends(require_owner),
    db: AsyncSession = Depends(get_db)
):
    """
    Owner-only endpoint to transfer ownership to another system user.
    """
    from app.db.models import SystemUser
    from sqlalchemy import func

    actor_id = current_user.get("user_id") or current_user.get("id")
    actor_name = current_user.get("name") or current_user.get("username")

    target_user = None
    if req.target_user_id:
        res = await db.execute(select(SystemUser).where(SystemUser.id == req.target_user_id))
        target_user = res.scalars().first()
    elif req.target_username:
        res = await db.execute(select(SystemUser).where(func.lower(SystemUser.username) == req.target_username.lower()))
        target_user = res.scalars().first()

    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")

    if target_user.id == actor_id:
        raise HTTPException(status_code=400, detail="You are already the owner.")

    # Demote previous owner
    prev_owner_res = await db.execute(select(SystemUser).where(SystemUser.id == actor_id))
    prev_owner_obj = prev_owner_res.scalars().first()
    if prev_owner_obj:
        prev_new_role = req.new_role_for_previous_owner or "admin"
        if prev_new_role not in ["admin", "staff", "operator"]:
            prev_new_role = "admin"
        prev_owner_obj.role = prev_new_role

    # Promote target user to OWNER
    target_user.role = Role.OWNER.value

    # Audit log
    await log_security_audit(
        db=db,
        actor_id=actor_id,
        actor_name=actor_name,
        actor_role="owner",
        action="TRANSFER_OWNERSHIP",
        target_entity=f"User:{target_user.username}",
        details=f"Owner transferred from {actor_name} to {target_user.username} ({target_user.full_name or ''})"
    )

    await db.commit()
    return {
        "success": True,
        "message": f"Ownership successfully transferred to {target_user.full_name or target_user.username}.",
        "new_owner": {
            "id": target_user.id,
            "username": target_user.username,
            "name": target_user.full_name or target_user.username,
            "role": target_user.role
        }
    }


class UpdateRoleRequest(BaseModel):
    role: str


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    req: UpdateRoleRequest,
    current_user: dict = Depends(require_owner),
    db: AsyncSession = Depends(get_db)
):
    """
    Owner-only endpoint to update any user's role.
    """
    from app.db.models import SystemUser

    new_role = req.role.strip().lower()
    valid_roles = [r.value for r in Role]
    if new_role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid_roles}")

    res = await db.execute(select(SystemUser).where(SystemUser.id == user_id))
    user = res.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    actor_id = current_user.get("user_id") or current_user.get("id")
    actor_name = current_user.get("name") or current_user.get("username")

    if user.id == actor_id and new_role != Role.OWNER.value:
        raise HTTPException(status_code=400, detail="Cannot demote yourself. Use Transfer Ownership instead.")

    old_role = user.role
    user.role = new_role

    await log_security_audit(
        db=db,
        actor_id=actor_id,
        actor_name=actor_name,
        actor_role="owner",
        action="CHANGE_USER_ROLE",
        target_entity=f"User:{user.username}",
        details=f"Changed role of {user.username} from {old_role} to {new_role}"
    )

    await db.commit()
    return {"success": True, "user_id": user.id, "username": user.username, "new_role": user.role}


@router.get("/audit-logs")
async def get_audit_logs(
    current_user: dict = Depends(require_owner),
    db: AsyncSession = Depends(get_db)
):
    """
    Owner-only endpoint to retrieve security and access audit logs.
    """
    from app.db.models import SecurityAuditLog

    res = await db.execute(select(SecurityAuditLog).order_by(SecurityAuditLog.timestamp.desc()).limit(100))
    logs = res.scalars().all()
    return {
        "success": True,
        "logs": [
            {
                "id": l.id,
                "actor_id": l.actor_id,
                "actor_name": l.actor_name,
                "actor_role": l.actor_role,
                "action": l.action,
                "target_entity": l.target_entity,
                "details": l.details,
                "timestamp": l.timestamp.isoformat() if l.timestamp else None
            }
            for l in logs
        ]
    }


@router.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    current_user: dict = Depends(require_owner),
    db: AsyncSession = Depends(get_db)
):
    """Owner-only endpoint to create system user accounts."""
    from app.db.models import SystemUser

    result = await db.execute(select(SystemUser).where(SystemUser.username == user_data.username))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Username already registered")

    new_user = SystemUser(
        username=user_data.username,
        hashed_password=get_password_hash(user_data.password),
        role=user_data.role.value if isinstance(user_data.role, Role) else str(user_data.role),
        is_active=True
    )
    db.add(new_user)

    actor_id = current_user.get("user_id") or current_user.get("id")
    actor_name = current_user.get("name") or current_user.get("username")
    await log_security_audit(
        db=db,
        actor_id=actor_id,
        actor_name=actor_name,
        actor_role="owner",
        action="CREATE_USER",
        target_entity=f"User:{user_data.username}",
        details=f"Created user {user_data.username} with role {new_user.role}"
    )

    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.get("/users", response_model=List[UserResponse])
async def list_users(
    current_user: dict = Depends(require_owner),
    db: AsyncSession = Depends(get_db)
):
    """Owner-only endpoint to list all system accounts."""
    from app.db.models import SystemUser

    result = await db.execute(select(SystemUser).order_by(SystemUser.id))
    return list(result.scalars().all())


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: dict = Depends(require_owner),
    db: AsyncSession = Depends(get_db)
):
    """Owner-only endpoint to delete user accounts."""
    from app.db.models import SystemUser

    result = await db.execute(select(SystemUser).where(SystemUser.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    actor_id = current_user.get("user_id") or current_user.get("id")
    if user.id == actor_id or user.username == current_user.get("username"):
        raise HTTPException(status_code=400, detail="Cannot delete current active owner account")

    actor_name = current_user.get("name") or current_user.get("username")
    await log_security_audit(
        db=db,
        actor_id=actor_id,
        actor_name=actor_name,
        actor_role="owner",
        action="DELETE_USER",
        target_entity=f"User:{user.username}",
        details=f"Deleted user account {user.username}"
    )

    await db.delete(user)
    await db.commit()
    return {"status": "User deleted"}
