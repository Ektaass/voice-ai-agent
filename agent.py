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
import os

import httpx

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
    async def get_weather(self, context: RunContext, city: str) -> str:
        """Get the current weather for a city using a live weather API."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                geo_resp = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": city, "count": 1, "language": "en", "format": "json"},
                )
                geo_resp.raise_for_status()
                results = geo_resp.json().get("results") or []
                if not results:
                    return f"I could not find the city {city}."

                location = results[0]
                weather_resp = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": location["latitude"],
                        "longitude": location["longitude"],
                        "current": (
                            "temperature_2m,relative_humidity_2m,"
                            "apparent_temperature,wind_speed_10m,weather_code"
                        ),
                        "timezone": "auto",
                    },
                )
                weather_resp.raise_for_status()
                current = weather_resp.json()["current"]

                return (
                    f"Current weather in {location['name']}, {location.get('country', '')}: "
                    f"{current['temperature_2m']} degrees Celsius, "
                    f"feels like {current['apparent_temperature']} degrees, "
                    f"humidity {current['relative_humidity_2m']} percent, "
                    f"wind speed {current['wind_speed_10m']} kilometers per hour."
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Weather lookup failed: %s", exc)
            return "Sorry, I could not get the weather right now."

    @function_tool()
    async def convert_currency(
        self,
        context: RunContext,
        amount: float,
        from_currency: str,
        to_currency: str,
    ) -> str:
        """Convert one currency into another using a live exchange-rate API."""
        try:
            from_currency = from_currency.upper()
            to_currency = to_currency.upper()
            if from_currency == to_currency:
                return f"{amount} {from_currency} is equal to {amount} {to_currency}."

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.frankfurter.dev/v1/latest",
                    params={"base": from_currency, "symbols": to_currency},
                )
                resp.raise_for_status()
                data = resp.json()

            rates = data.get("rates") or {}
            rate = rates.get(to_currency)
            if rate is None:
                return f"I couldn't convert {from_currency} to {to_currency}."

            return (
                f"{amount:.2f} {from_currency} is approximately "
                f"{amount * rate:.2f} {to_currency}."
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Currency conversion failed")
            return f"Sorry, I couldn't convert {amount} {from_currency} to {to_currency} right now. {exc}"

    @function_tool()
    async def web_search(self, context: RunContext, query: str) -> str:
        """Search the web for current information using Tavily."""
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return "The Tavily API key is not configured. Please add TAVILY_API_KEY to the environment."

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"query": query, "search_depth": "basic", "max_results": 3},
                )
                resp.raise_for_status()
                payload = resp.json()

            results = payload.get("results") or []
            if not results:
                return f"I could not find useful results for {query}."

            formatted_results = []
            for index, result in enumerate(results[:3], start=1):
                title = result.get("title", f"Result {index}")
                content = result.get("content", "")
                formatted_results.append(f"{title}: {content[:500]}")

            return "Here are the relevant search results: " + " ".join(formatted_results)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Web search tool failed: %s", exc)
            return "Sorry, I could not search the web right now."

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
