import asyncio
import base64
import json
import uuid
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig
from google.genai import types

from app.tools import current_call_id
from app.services import create_call, end_call
from app.db import SessionLocal
from app.agents import vma_runner, session_service

class VoiceBridge:
    def __init__(self, websocket: WebSocket):
        self.ws = websocket
        self.queue = LiveRequestQueue()
        self.call_id = None

    async def run(self) -> None:
        call = await create_call(SessionLocal, practice_id=1, status="started")
        self.call_id = call.id
        
        # Set context variable so tools know which call this is
        token = current_call_id.set(self.call_id)
        
        session_id = str(uuid.uuid4())
        await session_service.create_session(
            app_name="vma_app", 
            user_id="browser_user", 
            session_id=session_id
        )
        
        run_config = RunConfig(
            response_modalities=["AUDIO"],
            session_resumption=types.SessionResumptionConfig(),
        )
        
        async def upstream():
            """Reads browser audio and sends it to ADK."""
            try:
                async for data in self.ws.iter_text():
                    msg = json.loads(data)
                    if msg["type"] == "start":
                        # Send initial prompt to trigger greeting
                        self.queue.send_content(
                            types.Content(
                                parts=[types.Part(text="A patient just connected. Greet them now using the practice name and ask how you may help.")]
                            )
                        )
                    elif msg["type"] == "audio_in":
                        pcm = base64.b64decode(msg["payload"])
                        self.queue.send_realtime(
                            types.Blob(mime_type="audio/pcm;rate=16000", data=pcm)
                        )
                    elif msg["type"] == "stop":
                        break
            except WebSocketDisconnect:
                pass
            except Exception as e:
                print(f"[UPSTREAM ERROR]: {e}")
            finally:
                # CRITICAL: Always close the queue when the session ends
                self.queue.close()

        async def downstream():
            """Reads events from ADK and sends audio/text to browser."""
            try:
                async for event in vma_runner.run_live(
                    user_id="browser_user",
                    session_id=session_id,
                    live_request_queue=self.queue,
                    run_config=run_config
                ):
                    if event.error_code:
                        print(f"[MODEL ERROR]: {event.error_code} - {event.error_message}")
                        if event.error_code in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "MAX_TOKENS"):
                            break
                        continue
                        
                    # Handle Transcriptions
                    if event.input_transcription and event.input_transcription.text:
                        await self.ws.send_json({
                            "type": "transcript", 
                            "role": "user", 
                            "text": event.input_transcription.text
                        })
                    if event.output_transcription and event.output_transcription.text:
                        await self.ws.send_json({
                            "type": "transcript", 
                            "role": "assistant", 
                            "text": event.output_transcription.text
                        })
                        
                    # Handle Audio and Tool Calls
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.inline_data and part.inline_data.mime_type.startswith("audio/pcm"):
                                payload = base64.b64encode(part.inline_data.data).decode("utf-8")
                                await self.ws.send_json({
                                    "type": "audio_out",
                                    "payload": payload,
                                    "sample_rate": 24000
                                })
                            elif part.function_call:
                                await self.ws.send_json({
                                    "type": "tool_call",
                                    "name": part.function_call.name,
                                    "args": part.function_call.args
                                })
                                
            except Exception as e:
                print(f"[DOWNSTREAM ERROR]: {e}")
            finally:
                self.queue.close()

        try:
            await asyncio.gather(upstream(), downstream())
        except Exception as e:
            print(f"[VOICE BRIDGE ERROR]: {e}")
        finally:
            current_call_id.reset(token)
            self.queue.close()
            await end_call(SessionLocal, call_id=self.call_id, status="completed")