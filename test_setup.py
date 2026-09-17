"""
Quick sanity check — run this BEFORE `python agent.py dev`.

It checks:
  1. All required environment variables are present.
  2. Each provider's API key is actually valid (a real, lightweight network
     call to Groq, Deepgram and Cartesia; a local token-signing check for
     LiveKit, since generating a token needs no network call).

Usage:
    python test_setup.py
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

REQUIRED_VARS = [
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "GROQ_API_KEY",
    "DEEPGRAM_API_KEY",
    "CARTESIA_API_KEY",
]


def check_env_vars() -> bool:
    print("1. Checking environment variables...")
    missing = [v for v in REQUIRED_VARS if not os.getenv(v)]
    if missing:
        print(f"   FAILED - missing: {', '.join(missing)}")
        print("   -> Copy .env.example to .env and fill in real values.")
        return False
    print("   OK - all required variables are set.")
    return True


def check_livekit_token() -> bool:
    print("2. Checking LiveKit credentials (local token sign)...")
    try:
        from livekit import api

        token = (
            api.AccessToken(os.getenv("LIVEKIT_API_KEY"), os.getenv("LIVEKIT_API_SECRET"))
            .with_identity("test-setup-script")
            .with_grants(api.VideoGrants(room_join=True, room="test-room"))
            .to_jwt()
        )
        assert token
        print("   OK - LIVEKIT_API_KEY/SECRET can sign a valid token.")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"   FAILED - {e}")
        return False


def check_groq() -> bool:
    print("3. Checking Groq API key...")
    try:
        import httpx

        r = httpx.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
            timeout=10,
        )
        if r.status_code == 200:
            print("   OK - Groq key is valid.")
            return True
        print(f"   FAILED - Groq returned status {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"   FAILED - {e}")
        return False


def check_deepgram() -> bool:
    print("4. Checking Deepgram API key...")
    try:
        import httpx

        r = httpx.get(
            "https://api.deepgram.com/v1/projects",
            headers={"Authorization": f"Token {os.getenv('DEEPGRAM_API_KEY')}"},
            timeout=10,
        )
        if r.status_code == 200:
            print("   OK - Deepgram key is valid.")
            return True
        print(f"   FAILED - Deepgram returned status {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"   FAILED - {e}")
        return False


def check_cartesia() -> bool:
    print("5. Checking Cartesia API key...")
    try:
        import httpx

        r = httpx.get(
            "https://api.cartesia.ai/voices",
            headers={
                "X-API-Key": os.getenv("CARTESIA_API_KEY"),
                "Cartesia-Version": "2025-04-16",
            },
            timeout=10,
        )
        if r.status_code == 200:
            print("   OK - Cartesia key is valid.")
            return True
        print(f"   FAILED - Cartesia returned status {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"   FAILED - {e}")
        return False


def main() -> None:
    print("=== Voice AI Agent — setup check ===\n")

    if not check_env_vars():
        sys.exit(1)

    results = [
        check_livekit_token(),
        check_groq(),
        check_deepgram(),
        check_cartesia(),
    ]

    print()
    if all(results):
        print("All checks passed. You're ready to run: python agent.py dev")
    else:
        print("Some checks failed — fix the issues above before running the agent.")
        sys.exit(1)


if __name__ == "__main__":
    main()
