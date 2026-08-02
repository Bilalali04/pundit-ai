import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.agent.agent import SYSTEM_PROMPT
from src.agent.tools import (
    get_match_events,
    get_player_match_stats,
    get_player_season_baseline,
    get_position_expectations,
)

load_dotenv()


def main():
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
            ],
        ),
    )

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
