from __future__ import annotations
import contextvars

from app.db import SessionLocal
from app.config import settings
from app.services import get_practice, save_message, mark_call_escalated, update_call_intent

# Context variable to pass the call ID to tools without changing their signatures
current_call_id = contextvars.ContextVar("current_call_id", default=None)

async def get_practice_info() -> dict:
    """Get general practice information including name, address, office hours, accepted insurance, and new patient information."""
    async with SessionLocal() as session:
        practice = await get_practice(session, settings.default_practice_id)
    if not practice:
        return {"status": "error", "error": "practice_not_found"}
    return {
        "status": "success",
        "practice": {
            "name": practice.name,
            "address": practice.address,
            "office_hours": practice.office_hours,
            "accepted_insurance": practice.accepted_insurance or [],
            "new_patient_info": practice.new_patient_info,
        },
    }

async def get_office_hours() -> str:
    """Get the practice office hours."""
    async with SessionLocal() as session:
        practice = await get_practice(session, settings.default_practice_id)
    return practice.office_hours if practice else "Monday through Friday, 9am to 5pm"

async def get_location() -> str:
    """Get the practice address and location details."""
    async with SessionLocal() as session:
        practice = await get_practice(session, settings.default_practice_id)
    return practice.address if practice else "Address not available."

async def get_accepted_insurance() -> list[str]:
    """Get the list of accepted insurance plans."""
    async with SessionLocal() as session:
        practice = await get_practice(session, settings.default_practice_id)
    return practice.accepted_insurance if practice else []

async def take_message(
    caller_name: str, 
    dob: str, 
    reason: str, 
    callback_number: str, 
    confirmed: bool
) -> dict:
    """Save a message for the care team. Only call this after collecting caller name, date of birth, reason, and after the caller explicitly confirms the details. Pass an empty string for callback_number if not provided."""
    call_id = current_call_id.get()
    if not confirmed:
        return {"status": "error", "error": "confirmation_required"}
    if not dob or dob.lower() in {"refused", "unknown", "n/a"}:
        return {"status": "error", "error": "missing_dob"}
        
    # Handle empty or 'none' callback numbers since we removed the default
    if not callback_number or callback_number.lower() in {"none", "null", "n/a", ""}:
        callback_number = None
        
    async with SessionLocal() as session:
        msg = await save_message(
            session,
            practice_id=settings.default_practice_id,
            call_id=call_id,
            caller_name=caller_name,
            dob=dob,
            reason=reason,
            callback_number=callback_number,
            message_type="message",
            confirmed=True
        )
        await update_call_intent(session, call_id, "message")
        
    return {"status": "success", "message_id": msg.id}

async def request_callback(
    caller_name: str, 
    dob: str, 
    reason: str, 
    callback_number: str, 
    confirmed: bool
) -> dict:
    """Save a callback request for the care team. Only call this after collecting caller name, date of birth, reason, callback number if available, and after explicit caller confirmation. Pass an empty string for callback_number if not provided."""
    call_id = current_call_id.get()
    if not confirmed:
        return {"status": "error", "error": "confirmation_required"}
    if not dob or dob.lower() in {"refused", "unknown", "n/a"}:
        return {"status": "error", "error": "missing_dob"}
        
    # Handle empty or 'none' callback numbers since we removed the default
    if not callback_number or callback_number.lower() in {"none", "null", "n/a", ""}:
        callback_number = None
        
    async with SessionLocal() as session:
        msg = await save_message(
            session,
            practice_id=settings.default_practice_id,
            call_id=call_id,
            caller_name=caller_name,
            dob=dob,
            reason=reason,
            callback_number=callback_number,
            message_type="callback",
            confirmed=True
        )
        await update_call_intent(session, call_id, "callback")
        
    return {"status": "success", "message_id": msg.id}

async def escalate_to_human(reason: str) -> dict:
    """Escalate to a human VMA. Use this for emergencies, caller requests for a person, frustration, unclear requests, refused identity details, or anything you cannot safely resolve."""
    call_id = current_call_id.get()
    async with SessionLocal() as session:
        await mark_call_escalated(session, call_id)
        
    return {"status": "handoff_required", "reason": reason}

ALL_TOOLS = [
    get_practice_info,
    get_office_hours,
    get_location,
    get_accepted_insurance,
    take_message,
    request_callback,
    escalate_to_human
]

SYSTEM_INSTRUCTION = """
You are a Virtual Medical Assistant for Sunrise Medical.
Your tone must be warm, professional, calm, and clear. Do not sound robotic. Speak naturally.
Your job is to answer patient calls and help with routine practice requests.

CRITICAL FIRST STEP: As soon as the connection starts, you must speak first. Do not wait for the user. 
Greet the caller immediately by saying: "Thank you for calling Sunrise Medical. How may I help you today?"

Rules:
- Do not give medical advice, diagnose, or prescribe.
- If the caller describes an emergency, tell them to call emergency services immediately, then call escalate_to_human.
- For patient-specific requests, collect full name and date of birth.
- Before saving any message or callback request, repeat the details back and ask for confirmation.
- Only call take_message or request_callback with confirmed=true after the caller explicitly confirms.
- If the caller refuses date of birth, call escalate_to_human.
- If the caller asks for a human, call escalate_to_human.
- If you cannot resolve the request, call escalate_to_human.
- If a callback number is not provided, pass an empty string "" for the callback_number argument.
"""