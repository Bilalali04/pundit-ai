import os
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.agent.agent import SYSTEM_PROMPT
from src.agent.tools import (
    find_match,
    get_match_events,
    get_player_match_stats,
    get_player_season_baseline,
    get_position_expectations,
    get_team_matches,
    predict_match_outcome,
    search_web,
)

# Windows' default console codepage (often cp1252/cp437) mangles non-ASCII characters
# Gemini's responses routinely contain (curly apostrophes, en-dashes, etc.) - force UTF-8
# on stdout regardless of the console's codepage rather than relying on it being set
# externally (e.g. via PYTHONIOENCODING or `chcp 65001`).
sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()


def create_chat_session():
    """Create a new multi-turn Gemini chat session with the full tool set - the same setup
    used by the terminal chat loop below, reused as-is by src/web/ so the FastAPI backend
    doesn't duplicate this config. Each call returns an independent session with its own
    conversation memory (Gemini's Chat object accumulates history internally as
    send_message() is called), so callers needing multiple concurrent conversations (e.g.
    one per web session) should call this once per conversation, not share one instance.

    Returns (client, chat), NOT just chat - the Chat object depends on its parent Client's
    underlying HTTP client internally but does not itself hold a strong reference to it. If
    `client` isn't kept alive by the caller too, it gets garbage-collected once this function
    returns, closing the HTTP client under the Chat object's feet - confirmed directly: an
    explicit gc.collect() right after calling this (discarding client) reproduces
    `RuntimeError: Cannot send a request, as the client has been closed.` on the next
    send_message(). Callers must hold onto both for as long as the chat session is used.
    """
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    chat = client.chats.create(
        model="gemini-3.1-flash-lite",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[
                get_player_match_stats,
                get_player_season_baseline,
                get_match_events,
                get_position_expectations,
                find_match,
                get_team_matches,
                search_web,
                predict_match_outcome,
            ],
        ),
    )
    return client, chat


def main():
    _client, chat = create_chat_session()

    print("Pundit AI - ask about a player's match performance. Type 'quit' or 'exit' to stop.")
    while True:
        question = input("> ").strip()
        if question.lower() in ("quit", "exit"):
            break
        if not question:
            continue
        response = chat.send_message(question)
        print(response.text)


if __name__ == "__main__":
    main()
