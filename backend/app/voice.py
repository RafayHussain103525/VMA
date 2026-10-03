import asyncio
import base64
import json
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

from app.tools import current_call_id, SYSTEM_INSTRUCTION
from app.services import (
    create_call, end_call, get_practice, save_message, 
    mark_call_escalated, update_call_intent
)
from app.db import SessionLocal
from app.config import settings

client = genai.Client(api_key=settings.google_api_key)

TOOL_DECLARATIONS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(name="get_practice_info", description="Get general practice info.", parameters=types.Schema(type=types.Type.OBJECT, properties={})),
            types.FunctionDeclaration(name="get_office_hours", description="Get office hours.", parameters=types.Schema(type=types.Type.OBJECT, properties={})),
            types.FunctionDeclaration(name="get_location", description="Get address.", parameters=types.Schema(type=types.Type.OBJECT, properties={})),
            types.FunctionDeclaration(name="get_accepted_insurance", description="Get insurance.", parameters=types.Schema(type=types.Type.OBJECT, properties={})),
            types.FunctionDeclaration(name="get_doctor_name", description="Get doctor name.", parameters=types.Schema(type=types.Type.OBJECT, properties={})),
            types.FunctionDeclaration(name="get_medical_specialty", description="Get medical specialty.", parameters=types.Schema(type=types.Type.OBJECT, properties={})),
            types.FunctionDeclaration(
                name="take_message",
                description="Save a message. Only call after explicit confirmation.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "caller_name": types.Schema(type=types.Type.STRING),
                        "dob": types.Schema(type=types.Type.STRING),
                        "reason": types.Schema(type=types.Type.STRING),
                        "callback_number": types.Schema(type=types.Type.STRING),
                        "confirmed": types.Schema(type=types.Type.BOOLEAN)
                    },
                    required=["caller_name", "dob", "reason", "callback_number", "confirmed"]
                )
            ),
            types.FunctionDeclaration(
                name="request_callback",
                description="Save a callback request.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "caller_name": types.Schema(type=types.Type.STRING),
                        "dob": types.Schema(type=types.Type.STRING),
                        "reason": types.Schema(type=types.Type.STRING),
                        "callback_number": types.Schema(type=types.Type.STRING),
                        "confirmed": types.Schema(type=types.Type.BOOLEAN)
                    },
                    required=["caller_name", "dob", "reason", "callback_number", "confirmed"]
                )
            ),
            types.FunctionDeclaration(
                name="escalate_to_human",
                description="Escalate to a human.",
                parameters=types.Schema(type=types.Type.OBJECT, properties={"reason": types.Schema(type=types.Type.STRING)}, required=["reason"])
            )
        ]
    )
]

class VoiceBridge:
    def __init__(self, websocket: WebSocket):
        self.ws = websocket
        self.call_id = None

    async def run(self) -> None:
        call = await create_call(SessionLocal, practice_id=1, status="started")
        self.call_id = call.id
        
        token = current_call_id.set(self.call_id)
        
        try:
            print("[VOICE BRIDGE] Connecting to Gemini Live API...", flush=True)
            async with client.aio.live.connect(
                model=settings.gemini_model,
                config=types.LiveConnectConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    tools=TOOL_DECLARATIONS,
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                        )
                    ),
                    # 🔥 FIX 1: Explicitly enable high-sensitivity VAD for Barge-In
                    realtime_input_config=types.RealtimeInputConfig(
                        automatic_activity_detection=types.AutomaticActivityDetection(
                            disabled=False,
                            start_of_speech_sensitivity="START_SENSITIVITY_HIGH",
                            end_of_speech_sensitivity="END_SENSITIVITY_HIGH",
                            prefix_padding_ms=1000
                        )
                    ),
                    input_audio_transcription=types.AudioTranscriptionConfig(),
                    output_audio_transcription=types.AudioTranscriptionConfig()
                )
            ) as session:
                print("[VOICE BRIDGE] Connected to Gemini Live API!", flush=True)
                
                await self.ws.send_json({
                    "type": "ready",
                    "practice_name": "Sunrise Medical",
                    "model": settings.gemini_model
                })

                # Trigger greeting
                await session.send_realtime_input(
                    text="A patient just connected. Please greet them now using the practice name and ask how you may help."
                )

                async def upstream():
                    try:
                        print("[UPSTREAM] Listening for frontend messages...", flush=True)
                        async for data in self.ws.iter_text():
                            msg = json.loads(data)
                            msg_type = msg.get("type")
                            
                            if msg_type == "audio_in":
                                pcm = base64.b64decode(msg["payload"])
                                await session.send_realtime_input(
                                    audio=types.Blob(mime_type="audio/pcm;rate=16000", data=pcm)
                                )
                            elif msg_type == "stop":
                                print("[UPSTREAM] Received stop signal.", flush=True)
                                break
                    except WebSocketDisconnect:
                        print("[UPSTREAM] Frontend disconnected.", flush=True)
                    except Exception as e:
                        print(f"[UPSTREAM ERROR]: {e}", flush=True)

                async def downstream():
                    try:
                        print("[DOWNSTREAM] Listening for Gemini events...", flush=True)
                        while True:
                            async for event in session.receive():
                                if event.tool_call:
                                    function_responses = []
                                    for fc in event.tool_call.function_calls:
                                        print(f"[DOWNSTREAM] Tool call: {fc.name}({fc.args})", flush=True)
                                        result = await self._execute_tool(fc.name, fc.args)
                                        
                                        # Send the dictionary result back to Gemini
                                        function_responses.append(
                                            types.FunctionResponse(
                                                id=fc.id,
                                                name=fc.name,
                                                response=result
                                            )
                                        )
                                    
                                    await session.send_tool_response(function_responses=function_responses)
                                
                                if event.server_content:
                                    if event.server_content.model_turn:
                                        for part in event.server_content.model_turn.parts:
                                            if part.inline_data and part.inline_data.mime_type.startswith("audio/pcm"):
                                                payload = base64.b64encode(part.inline_data.data).decode("utf-8")
                                                await self.ws.send_json({
                                                    "type": "audio_out",
                                                    "payload": payload,
                                                    "sample_rate": 24000
                                                })
                                    
                                    if event.server_content.input_transcription:
                                        await self.ws.send_json({
                                            "type": "transcript",
                                            "role": "user",
                                            "text": event.server_content.input_transcription.text
                                        })
                                    if event.server_content.output_transcription:
                                        await self.ws.send_json({
                                            "type": "transcript",
                                            "role": "assistant",
                                            "text": event.server_content.output_transcription.text
                                        })
                                        
                            print("[DOWNSTREAM] Iterator ended, attempting to re-enter...", flush=True)
                            await asyncio.sleep(0.5)
                            
                    except Exception as e:
                        print(f"[DOWNSTREAM ERROR]: {e}", flush=True)

                upstream_task = asyncio.create_task(upstream())
                downstream_task = asyncio.create_task(downstream())

                done, pending = await asyncio.wait(
                    [upstream_task, downstream_task],
                    return_when=asyncio.FIRST_COMPLETED
                )

                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

        except Exception as e:
            print(f"[VOICE BRIDGE ERROR]: {e}", flush=True)
        finally:
            current_call_id.reset(token)
            await end_call(SessionLocal, call_id=self.call_id, status="completed")

    async def _execute_tool(self, name: str, args: dict) -> dict:
        if name == "get_practice_info":
            async with SessionLocal() as session:
                practice = await get_practice(session, settings.default_practice_id)
            if not practice: return {"status": "error", "error": "practice_not_found"}
            return {
                "status": "success", 
                "name": practice.name, 
                "address": practice.address, 
                "office_hours": practice.office_hours, 
                "accepted_insurance": practice.accepted_insurance or [], 
                "new_patient_info": practice.new_patient_info
            }
        
        elif name == "get_office_hours":
            async with SessionLocal() as session:
                practice = await get_practice(session, settings.default_practice_id)
            # 🔥 FIX: Wrap the string in a dictionary
            return {"office_hours": practice.office_hours if practice else "Monday through Friday, 9am to 5pm"}
            
        elif name == "get_location":
            async with SessionLocal() as session:
                practice = await get_practice(session, settings.default_practice_id)
            # 🔥 FIX: Wrap the string in a dictionary
            return {"address": practice.address if practice else "Address not available."}
            
        elif name == "get_accepted_insurance":
            async with SessionLocal() as session:
                practice = await get_practice(session, settings.default_practice_id)
            # 🔥 FIX: Wrap the list in a dictionary
            return {"accepted_insurance": practice.accepted_insurance if practice else []}
        
        elif name == "get_doctor_name":
            async with SessionLocal() as session:
                practice = await get_practice(session, settings.default_practice_id)
            return {"doctor_name": practice.doctor_name if practice else "Doctor not available."}
            
        elif name == "get_medical_specialty":
            async with SessionLocal() as session:
                practice = await get_practice(session, settings.default_practice_id)
            return {"medical_specialty": practice.medical_specialty if practice else "Specialty not available."}
            
        elif name == "take_message":
            call_id = current_call_id.get()
            if not args.get("confirmed"): return {"status": "error", "error": "confirmation_required"}
            if not args.get("dob"): return {"status": "error", "error": "missing_dob"}
            cb = args.get("callback_number")
            if not cb or cb.lower() in {"none", "null", "n/a", ""}: cb = None
            msg = await save_message(SessionLocal, practice_id=settings.default_practice_id, call_id=call_id, caller_name=args["caller_name"], dob=args["dob"], reason=args["reason"], callback_number=cb, message_type="message", confirmed=True)
            await update_call_intent(SessionLocal, call_id, "message")
            return {"status": "success", "message_id": msg.id}
            
        elif name == "request_callback":
            call_id = current_call_id.get()
            if not args.get("confirmed"): return {"status": "error", "error": "confirmation_required"}
            if not args.get("dob"): return {"status": "error", "error": "missing_dob"}
            cb = args.get("callback_number")
            if not cb or cb.lower() in {"none", "null", "n/a", ""}: cb = None
            msg = await save_message(SessionLocal, practice_id=settings.default_practice_id, call_id=call_id, caller_name=args["caller_name"], dob=args["dob"], reason=args["reason"], callback_number=cb, message_type="callback", confirmed=True)
            await update_call_intent(SessionLocal, call_id, "callback")
            return {"status": "success", "message_id": msg.id}
            
        elif name == "escalate_to_human":
            call_id = current_call_id.get()
            await mark_call_escalated(SessionLocal, call_id)
            return {"status": "handoff_required", "reason": args.get("reason")}
            
        return {"status": "error", "error": "unknown_tool"}