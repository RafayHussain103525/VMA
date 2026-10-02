import pytest
import pytest_asyncio

from app.db import SessionLocal, engine
from app.models import Base
from app.services import create_call, ensure_default_practice
from app.tools import ToolContext, execute_tool


async def fake_send_event(payload: dict) -> None:
    # Tests do not need a real WebSocket.
    return None


@pytest_asyncio.fixture
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        await ensure_default_practice(session, 1)

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_get_office_hours(setup_db):
    call = await create_call(SessionLocal, practice_id=1)

    ctx = ToolContext(
        session_factory=SessionLocal,
        practice_id=1,
        call_id=call.id,
        send_event=fake_send_event,
    )

    result = await execute_tool("get_office_hours", {}, ctx)

    assert result["status"] == "success"
    assert "office_hours" in result


@pytest.mark.asyncio
async def test_request_callback_requires_confirmation(setup_db):
    call = await create_call(SessionLocal, practice_id=1)

    ctx = ToolContext(
        session_factory=SessionLocal,
        practice_id=1,
        call_id=call.id,
        send_event=fake_send_event,
    )

    result = await execute_tool(
        "request_callback",
        {
            "caller_name": "John Test",
            "dob": "1990-01-01",
            "reason": "Medication refill",
            "callback_number": "555-123-4567",
            "confirmed": False,
        },
        ctx,
    )

    assert result["status"] == "error"
    assert result["error"] == "confirmation_required"


@pytest.mark.asyncio
async def test_request_callback_success(setup_db):
    call = await create_call(SessionLocal, practice_id=1)

    ctx = ToolContext(
        session_factory=SessionLocal,
        practice_id=1,
        call_id=call.id,
        send_event=fake_send_event,
    )

    result = await execute_tool(
        "request_callback",
        {
            "caller_name": "John Test",
            "dob": "1990-01-01",
            "reason": "Medication refill",
            "callback_number": "555-123-4567",
            "confirmed": True,
        },
        ctx,
    )

    assert result["status"] == "success"
    assert "message_id" in result


@pytest.mark.asyncio
async def test_request_callback_rejects_refused_dob(setup_db):
    call = await create_call(SessionLocal, practice_id=1)

    ctx = ToolContext(
        session_factory=SessionLocal,
        practice_id=1,
        call_id=call.id,
        send_event=fake_send_event,
    )

    result = await execute_tool(
        "request_callback",
        {
            "caller_name": "John Test",
            "dob": "refused",
            "reason": "Medication refill",
            "callback_number": "555-123-4567",
            "confirmed": True,
        },
        ctx,
    )

    assert result["status"] == "error"
    assert result["error"] == "missing_or_invalid_dob"


@pytest.mark.asyncio
async def test_escalation(setup_db):
    call = await create_call(SessionLocal, practice_id=1)

    ctx = ToolContext(
        session_factory=SessionLocal,
        practice_id=1,
        call_id=call.id,
        send_event=fake_send_event,
    )

    result = await execute_tool(
        "escalate_to_human",
        {
            "reason": "Caller asked for a person.",
        },
        ctx,
    )

    assert result["status"] == "handoff_required"
    assert ctx.escalated is True