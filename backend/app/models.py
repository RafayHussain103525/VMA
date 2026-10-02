from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# Use JSONB on PostgreSQL, but allow SQLite for tests.
PortableJSON = JSONB().with_variant(JSON(), "sqlite")


class Base(DeclarativeBase):
    pass


class Practice(Base):
    __tablename__ = "practices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    office_hours: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    accepted_insurance: Mapped[Any] = mapped_column(PortableJSON, default=list)
    new_patient_info: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    escalation_phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ehr_type: Mapped[str] = mapped_column(String(32), default="none")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    calls: Mapped[list["Call"]] = relationship(back_populates="practice")
    messages: Mapped[list["Message"]] = relationship(back_populates="practice")


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    practice_id: Mapped[int] = mapped_column(
        ForeignKey("practices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Browser demo session ID, later can be Twilio call SID.
    session_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    intent: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="started")
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    practice: Mapped["Practice"] = relationship(back_populates="calls")
    messages: Mapped[list["Message"]] = relationship(back_populates="call")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="call")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    practice_id: Mapped[int] = mapped_column(
        ForeignKey("practices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    call_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("calls.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    caller_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dob: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    callback_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    message_type: Mapped[str] = mapped_column(String(32), default="message")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    practice: Mapped["Practice"] = relationship(back_populates="messages")
    call: Mapped[Optional["Call"]] = relationship(back_populates="messages")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("calls.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="success")

    metadata_: Mapped[Any] = mapped_column(
        "metadata",
        PortableJSON,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    call: Mapped[Optional["Call"]] = relationship(back_populates="audit_logs")