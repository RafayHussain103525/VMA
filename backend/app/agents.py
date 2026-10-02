from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from app.tools import ALL_TOOLS, SYSTEM_INSTRUCTION

# Define the ADK Agent
vma_agent = Agent(
    name="vma_agent",
    model="gemini-3.8-live",
    tools=ALL_TOOLS,
    instruction=SYSTEM_INSTRUCTION,
)

# ADK handles session state and memory
session_service = InMemorySessionService()

# The Runner drives the agent and yields events
vma_runner = Runner(
    app_name="vma_app",
    agent=vma_agent,
    session_service=session_service,
)