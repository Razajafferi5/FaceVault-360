from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, Integer, Float, Text, LargeBinary, ForeignKey, func, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_identifier: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(100))
    role: Mapped[Optional[str]] = mapped_column(String(50))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='active')
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    embeddings: Mapped[List["FaceEmbedding"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    access_events: Mapped[List["AccessEvent"]] = relationship(
        back_populates="person"
    )
    attendances: Mapped[List["Attendance"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    unknown_events: Mapped[List["UnknownPersonEvent"]] = relationship(
        back_populates="enrolled_person"
    )

    def __repr__(self) -> str:
        return f"<Person(id={self.id}, name='{self.name}', status='{self.status}')>"

class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), index=True)
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    faiss_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    pose_label: Mapped[str] = mapped_column(String(20), nullable=False)
    yaw: Mapped[float] = mapped_column(Float)
    pitch: Mapped[float] = mapped_column(Float)
    roll: Mapped[float] = mapped_column(Float)
    quality_score: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    person: Mapped["Person"] = relationship(back_populates="embeddings")

    def __repr__(self) -> str:
        return f"<FaceEmbedding(id={self.id}, person_id={self.person_id}, pose='{self.pose_label}')>"

class AccessEvent(Base):
    __tablename__ = "access_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    person_id: Mapped[Optional[int]] = mapped_column(ForeignKey("persons.id"), index=True)
    recognized_name: Mapped[Optional[str]] = mapped_column(String(100))
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), index=True)
    authorization_result: Mapped[str] = mapped_column(String(20))
    pose_yaw: Mapped[Optional[float]] = mapped_column(Float)
    pose_pitch: Mapped[Optional[float]] = mapped_column(Float)
    quality_score: Mapped[Optional[float]] = mapped_column(Float)
    camera_id: Mapped[str] = mapped_column(String(50), default='default')
    failure_reason: Mapped[Optional[str]] = mapped_column(String(100))

    person: Mapped[Optional["Person"]] = relationship(back_populates="access_events")

    def __repr__(self) -> str:
        return f"<AccessEvent(id={self.id}, status='{self.status}', result='{self.authorization_result}')>"

class SystemUser(Base):
    __tablename__ = "system_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True, nullable=True)
    role: Mapped[str] = mapped_column(String(20), default='viewer')
    is_active: Mapped[bool] = mapped_column(default=True)
    person_id: Mapped[Optional[int]] = mapped_column(ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    def __repr__(self) -> str:
        return f"<SystemUser(username='{self.username}', role='{self.role}')>"

class Attendance(Base):
    __tablename__ = "attendances"
    __table_args__ = (
        Index("ix_attendances_employee_date", "employee_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), index=True)
    employee_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date: Mapped[str] = mapped_column(String(20), index=True)  # e.g. "14-09-2026"
    time: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "09:15 AM"
    status: Mapped[str] = mapped_column(String(20), default="Present")
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    check_in_time: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    check_out_time: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    check_in_camera: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    check_out_camera: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    person: Mapped["Person"] = relationship(back_populates="attendances")

    def __repr__(self) -> str:
        return f"<Attendance(id={self.id}, employee_id={self.employee_id}, name='{self.employee_name}', date='{self.date}', time='{self.time}')>"


class RTSPCamera(Base):
    __tablename__ = "rtsp_cameras"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rtsp_url: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), default="CHECK-IN")  # "CHECK-IN", "CHECK-OUT", "COMBINED"
    enabled: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(20), default="disconnected")  # "connected", "disconnected", "reconnecting"
    last_seen: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<RTSPCamera(id={self.id}, name='{self.name}', mode='{self.mode}', status='{self.status}')>"


class UnknownPersonEvent(Base):
    __tablename__ = "unknown_person_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_uuid: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    detected_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    date_str: Mapped[str] = mapped_column(String(20), index=True)  # e.g. "18-09-2026"
    time_str: Mapped[str] = mapped_column(String(20))              # e.g. "10:42 AM"
    camera_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    camera_name: Mapped[str] = mapped_column(String(100))
    camera_role: Mapped[str] = mapped_column(String(20), index=True)  # "CHECK-IN" or "CHECK-OUT"
    snapshot_path: Mapped[str] = mapped_column(String(255))
    snapshot_url: Mapped[str] = mapped_column(String(255))
    face_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    recognition_status: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    access_status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)  # PENDING, APPROVED, DENIED, ENROLLED
    # Sessionization & Deduplication fields
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    first_seen_time_str: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last_seen_time_str: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    detection_count: Mapped[int] = mapped_column(Integer, default=1)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    best_quality_score: Mapped[float] = mapped_column(Float, default=0.0)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit Trail
    approved_by_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    approved_by_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    denied_by_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    denied_by_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    denied_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    enrolled_person_id: Mapped[Optional[int]] = mapped_column(ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    enrollment_method: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # "RTSP" or "WEBCAM"
    enrolled_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    enrolled_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    enrolled_person: Mapped[Optional["Person"]] = relationship(back_populates="unknown_events")

    def __repr__(self) -> str:
        return f"<UnknownPersonEvent(id={self.id}, uuid='{self.event_uuid}', camera='{self.camera_name}', status='{self.access_status}')>"


class SecurityAuditLog(Base):
    __tablename__ = "security_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_entity: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)

    def __repr__(self) -> str:
        return f"<SecurityAuditLog(id={self.id}, action='{self.action}', actor='{self.actor_name}')>"



