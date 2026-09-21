from collections.abc import AsyncGenerator
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncAttrs
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

# Apply SQLite specific pragmas for performance and concurrency
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

class Base(AsyncAttrs, DeclarativeBase):
    pass

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_db() -> None:
    from app.db.models import Base as ModelsBase
    from sqlalchemy import text
    async with engine.begin() as conn:
        # Create tables
        await conn.run_sync(ModelsBase.metadata.create_all)
        
        # Backward compatibility column check for attendances
        try:
            res = await conn.execute(text("PRAGMA table_info(attendances)"))
            existing_cols = {r[1] for r in res.fetchall()}
            needed_cols = [
                ("check_in_time", "VARCHAR(20)"),
                ("check_out_time", "VARCHAR(20)"),
                ("check_in_camera", "VARCHAR(100)"),
                ("check_out_camera", "VARCHAR(100)")
            ]
            for col_name, col_type in needed_cols:
                if col_name not in existing_cols:
                    await conn.execute(text(f"ALTER TABLE attendances ADD COLUMN {col_name} {col_type}"))

            # Backward compatibility column check for system_users
            res_u = await conn.execute(text("PRAGMA table_info(system_users)"))
            existing_user_cols = {r[1] for r in res_u.fetchall()}
            needed_user_cols = [
                ("full_name", "VARCHAR(150)"),
                ("email", "VARCHAR(150)"),
                ("person_id", "INTEGER")
            ]
            for col_name, col_type in needed_user_cols:
                if col_name not in existing_user_cols:
                    await conn.execute(text(f"ALTER TABLE system_users ADD COLUMN {col_name} {col_type}"))

            # Backward compatibility column check for unknown_person_events
            res_e = await conn.execute(text("PRAGMA table_info(unknown_person_events)"))
            existing_event_cols = {r[1] for r in res_e.fetchall()}
            needed_event_cols = [
                ("enrollment_method", "VARCHAR(20)"),
                ("enrolled_by", "VARCHAR(100)"),
                ("enrolled_at", "TIMESTAMP"),
                ("first_seen_at", "TIMESTAMP"),
                ("last_seen_at", "TIMESTAMP"),
                ("first_seen_time_str", "VARCHAR(20)"),
                ("last_seen_time_str", "VARCHAR(20)"),
                ("detection_count", "INTEGER DEFAULT 1"),
                ("duration_seconds", "INTEGER DEFAULT 0"),
                ("best_quality_score", "FLOAT DEFAULT 0.0")
            ]
            for col_name, col_type in needed_event_cols:
                if col_name not in existing_event_cols:
                    await conn.execute(text(f"ALTER TABLE unknown_person_events ADD COLUMN {col_name} {col_type}"))

            # Authoritative Account Initialization & Person Linkage
            from app.core.security import get_password_hash
            from app.core.config import get_settings
            cfg = get_settings()

            # Ensure Owner account exists with role='owner' and person_id=1
            owner_pw_hash = get_password_hash("ownerpassword123")
            admin_pw_hash = get_password_hash(cfg.ADMIN_PASSWORD)
            usman_pw_hash = get_password_hash("usman123")
            rabia_pw_hash = get_password_hash("rabia123")

            # Set user #1 ('owner') to OWNER and link to Person #1
            await conn.execute(text("""
                UPDATE system_users 
                SET role = 'owner', person_id = 1, full_name = 'Syed Raza Abbas'
                WHERE username = 'owner' OR id = 1 OR username = :admin_user
            """), {"admin_user": cfg.ADMIN_USERNAME})

            # If user #3 (Raza Gardezi) or #4 (razajaffery14@gmail.com) is Syed Raza Abbas, set to owner and person_id=1
            await conn.execute(text("""
                UPDATE system_users 
                SET role = 'owner', person_id = 1, full_name = 'Syed Raza Abbas'
                WHERE username LIKE '%raza%' OR email LIKE '%raza%' OR full_name LIKE '%raza%'
            """))

            # Check if 'owner' account exists, if not insert
            res_chk = await conn.execute(text("SELECT id FROM system_users WHERE username = 'owner'"))
            if not res_chk.fetchone():
                await conn.execute(text("""
                    INSERT INTO system_users (username, hashed_password, full_name, email, role, is_active, person_id)
                    VALUES ('owner', :pw, 'Syed Raza Abbas', 'owner@facevault360.com', 'owner', 1, 1)
                """), {"pw": owner_pw_hash})

            # Check if 'usman' staff account exists, if not insert (linked to Person #3)
            res_u_chk = await conn.execute(text("SELECT id FROM system_users WHERE username = 'usman'"))
            if not res_u_chk.fetchone():
                await conn.execute(text("""
                    INSERT INTO system_users (username, hashed_password, full_name, email, role, is_active, person_id)
                    VALUES ('usman', :pw, 'usman', 'usman@facevault360.com', 'staff', 1, 3)
                """), {"pw": usman_pw_hash})
            else:
                await conn.execute(text("""
                    UPDATE system_users SET role = 'staff', person_id = 3, full_name = 'usman'
                    WHERE username = 'usman'
                """))

            # Check if 'rabia' staff account exists, if not insert (linked to Person #4)
            res_r_chk = await conn.execute(text("SELECT id FROM system_users WHERE username = 'rabia'"))
            if not res_r_chk.fetchone():
                await conn.execute(text("""
                    INSERT INTO system_users (username, hashed_password, full_name, email, role, is_active, person_id)
                    VALUES ('rabia', :pw, 'rabia', 'rabia@facevault360.com', 'staff', 1, 4)
                """), {"pw": rabia_pw_hash})
            else:
                await conn.execute(text("""
                    UPDATE system_users SET role = 'staff', person_id = 4, full_name = 'rabia'
                    WHERE username = 'rabia'
                """))

        except Exception as e:
            print(f"Warning during table schema migration or account seed: {e}")




async def close_db() -> None:
    await engine.dispose()
