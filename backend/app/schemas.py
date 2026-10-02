from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MessageCreate(BaseModel):
    practice_id: int = 1
    call_id: Optional[int] = None
    caller_name: str = Field(min_length=1)
    dob: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    callback_number: Optional[str] = None
    message_type: str = "message"
    confirmed: bool = True


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    practice_id: int
    call_id: Optional[int]
    caller_name: Optional[str]
    dob: Optional[str]
    callback_number: Optional[str]
    reason: Optional[str]
    message_type: str
    status: str
    confirmed: bool
    created_at: datetime


class CallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    practice_id: int
    session_id: Optional[str]
    intent: Optional[str]
    status: str
    escalated: bool
    summary: Optional[str]
    started_at: datetime
    ended_at: Optional[datetime]