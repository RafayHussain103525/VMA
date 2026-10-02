from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import AuditLog, Call, Message, Practice


DEFAULT_PRACTICE_SEED = {
    "name": "Sunrise Medical",
    "phone_number": "+15550001111",
    "address": "123 Medical Plaza, Suite 200",
    "office_hours": "Monday through Friday, 9am to 5pm",
    "accepted_insurance": [
        "Medicare",
        "Medicaid",
        "Aetna",
        "Blue Cross",
    ],
    "new_patient_info": "We are accepting new patients.",
    "escalation_phone": "+15552223333",
    "ehr_type": "none",
}


async def ensure_default_practice(
    session: AsyncSession,
    practice_id: int,
) -> Practice:
    practice = await session.get(Practice, practice_id)
    if practice:
        return practice

    practice = Practice(
        id=practice_id,
        **DEFAULT_PRACTICE_SEED,
    )
    session.add(practice)
    await session.commit()
    await session.refresh(practice)
    return practice


async def get_practice(
    session: AsyncSession,
    practice_id: int,
) -> Optional[Practice]:
    return await session.get(Practice, practice_id)


async def create_call(
    session_factory: async_sessionmaker[AsyncSession],
    practice_id: int,
    session_id: Optional[str] = None,
    status: str = "started",
) -> Call:
    async with session_factory() as session:
        call = Call(
            practice_id=practice_id,
            session_id=session_id,
            status=status,
            escalated=False,
        )
        session.add(call)
        await session.commit()
        await session.refresh(call)
        return call


async def end_call(
    session_factory: async_sessionmaker[AsyncSession],
    call_id: int,
    status: str = "completed",
    escalated: bool = False,
    summary: Optional[str] = None,
) -> None:
    async with session_factory() as session:
        await session.execute(
            update(Call)
            .where(Call.id == call_id)
            .values(
                status=status,
                escalated=escalated,
                summary=summary,
                ended_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def update_call_intent(
    session_factory: async_sessionmaker[AsyncSession],
    call_id: int,
    intent: str,
) -> None:
    async with session_factory() as session:
        await session.execute(
            update(Call)
            .where(Call.id == call_id)
            .values(intent=intent)
        )
        await session.commit()


async def mark_call_escalated(
    session_factory: async_sessionmaker[AsyncSession],
    call_id: int,
) -> None:
    async with session_factory() as session:
        await session.execute(
            update(Call)
            .where(Call.id == call_id)
            .values(escalated=True)
        )
        await session.commit()


async def save_message(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    practice_id: int,
    call_id: Optional[int],
    caller_name: str,
    dob: str,
    reason: str,
    callback_number: Optional[str] = None,
    message_type: str = "message",
    confirmed: bool = False,
) -> Message:
    async with session_factory() as session:
        message = Message(
            practice_id=practice_id,
            call_id=call_id,
            caller_name=caller_name,
            dob=dob,
            callback_number=callback_number,
            reason=reason,
            message_type=message_type,
            status="pending",
            confirmed=confirmed,
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
        return message


async def log_audit(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    call_id: Optional[int],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    status: str = "success",
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    async with session_factory() as session:
        audit = AuditLog(
            call_id=call_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            status=status,
            metadata_=metadata or {},
        )
        session.add(audit)
        await session.commit()


async def list_messages(
    session_factory: async_sessionmaker[AsyncSession],
    practice_id: int,
    limit: int = 100,
) -> list[Message]:
    async with session_factory() as session:
        result = await session.execute(
            select(Message)
            .where(Message.practice_id == practice_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def list_calls(
    session_factory: async_sessionmaker[AsyncSession],
    practice_id: int,
    limit: int = 100,
) -> list[Call]:
    async with session_factory() as session:
        result = await session.execute(
            select(Call)
            .where(Call.practice_id == practice_id)
            .order_by(Call.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())