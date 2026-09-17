"""
Voice AI Agent — LiveKit Agents (v1.x) + Groq LLM + Deepgram STT + Cartesia TTS

Flow:
    User speaks
      -> LiveKit room (audio track)
      -> Deepgram STT (speech -> text)
      -> Groq LLM (text -> response text)
      -> Cartesia TTS (response text -> speech)
      -> User hears the agent's reply

Run locally:
    python agent.py console      # quick terminal test (no LiveKit Playground needed)
    python agent.py dev          # connects to LiveKit Cloud, worker waits for a room
                                  # (used together with LiveKit Playground)
"""

import logging

from dotenv import load_dotenv

from livekit import agents
from livekit.agents import Agent, AgentSession, JobContext, RoomInputOptions, WorkerOptions, RunContext, function_tool, cli
from livekit.plugins import cartesia, deepgram, groq, silero

# Load variables from .env before anything else touches os.environ
load_dotenv()

logger = logging.getLogger("voice-agent")


class Assistant(Agent):
    """Defines the agent's persona and behaviour."""

    @function_tool()
    async def calculate(self, context: RunContext, expression: str) -> str:
        """Calculate a mathematical expression."""
        try:
            result = eval(expression, {"__builtins__": {}}, {})
            return f"The result is {result}."
        except Exception:
            return "Sorry, I could not calculate that."

    @function_tool()
    async def get_current_time(self, context: RunContext) -> str:
        """Get the current local date and time."""
        from datetime import datetime

        now = datetime.now()
        return now.strftime("The current date and time is %A, %B %d, %Y at %I:%M %p.")

    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are a friendly, helpful voice assistant speaking with the user out loud. "
                "Keep replies short, natural and conversational (1-3 sentences) since this is "
                "a spoken conversation, not a chat window. Avoid lists, markdown, emojis or "
                "special characters, since they don't translate well to speech. "
                "If you don't understand the user, politely ask them to repeat themselves."
            )
        )


async def entrypoint(ctx: JobContext) -> None:
    """Called by the LiveKit Agents worker whenever it is assigned a job (a room)."""

    # Connect the agent to the LiveKit room for this job
    await ctx.connect()

    # Build the voice pipeline: STT -> LLM -> TTS, with VAD for turn-taking
    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="en-US"),
        llm=groq.LLM(model="openai/gpt-oss-20b"),
        tts=cartesia.TTS(model="sonic-3", language="en"),
        vad=silero.VAD.load(),
    )

    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_input_options=RoomInputOptions(),
    )

    # Agent greets the user first, so there's something to hear immediately
    # after connecting from the Playground.
    await session.generate_reply(
        instructions="Greet the user briefly and ask how you can help them today."
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
