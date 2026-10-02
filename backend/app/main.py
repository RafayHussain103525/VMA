from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db import SessionLocal, init_db
from app.schemas import CallOut, MessageCreate, MessageOut
from app.services import (
    list_calls,
    list_messages,
    log_audit,
    save_message,
)
from app.voice import VoiceBridge

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(
    title="VMA AI Phase 1",
    version="0.1.0",
    lifespan=lifespan,
)

# FIX 1: CORS Configuration
# Browsers block allow_origins=["*"] when allow_credentials=True.
# We set allow_credentials=False to allow the wildcard origin for local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False, 
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.environment,
        "model": settings.gemini_model,
    }

@app.get("/messages", response_model=list[MessageOut])
async def get_messages(
    practice_id: int = Query(default=1),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[MessageOut]:
    messages = await list_messages(
        SessionLocal,
        practice_id=practice_id,
        limit=limit,
    )
    return [MessageOut.model_validate(message) for message in messages]

@app.get("/calls", response_model=list[CallOut])
async def get_calls(
    practice_id: int = Query(default=1),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[CallOut]:
    calls = await list_calls(
        SessionLocal,
        practice_id=practice_id,
        limit=limit,
    )
    return [CallOut.model_validate(call) for call in calls]

@app.post("/messages", response_model=MessageOut, status_code=201)
async def create_message(body: MessageCreate) -> MessageOut:
    try:
        message = await save_message(
            SessionLocal,
            practice_id=body.practice_id,
            call_id=body.call_id,
            caller_name=body.caller_name,
            dob=body.dob,
            reason=body.reason,
            callback_number=body.callback_number,
            message_type=body.message_type,
            confirmed=body.confirmed,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="failed_to_save_message") from exc

    await log_audit(
        SessionLocal,
        call_id=body.call_id,
        action="message_created_via_api",
        entity_type="message",
        entity_id=str(message.id),
        status="success",
        metadata={"message_type": message.message_type},
    )

    return MessageOut.model_validate(message)

@app.websocket("/ws/voice")
async def websocket_voice(websocket: WebSocket) -> None:
    await websocket.accept()

    bridge = VoiceBridge(websocket=websocket)

    await bridge.run()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")