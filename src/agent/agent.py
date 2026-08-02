import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.agent.tools import get_match_events, get_player_match_stats, get_player_season_baseline

load_dotenv()

SYSTEM_PROMPT = (
    "You are a football analyst. When asked about a player's performance in a match, "
    "use the get_player_match_stats tool to retrieve their real stats, then form your own "
    "opinion about how well they played - don't just repeat the numbers back. Weigh the stats "
    "in context (e.g. a defender's tackles and interceptions matter more than a winger's), and "
    "give a clear, opinionated verdict, not a stat dump.\n\n"
    "A raw count is meaningless without knowing the attempt volume behind it - always compute "
    "and consider rates/percentages where a total and a completed/successful count are both "
    "available (e.g. pass completion = passes_completed / passes_total, duel success = "
    "duels_won / duels_total), rather than reacting to the completed/successful count in "
    "isolation. A low completed count with a high total can still be a strong rate, and vice "
    "versa - judge the rate, not just the raw number."
)


def ask(question: str) -> str:
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=question,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[get_player_match_stats, get_player_season_baseline, get_match_events],
        ),
    )

    print("=== Tool-calling history ===")
    for content in response.automatic_function_calling_history or []:
        for part in content.parts:
            if part.function_call:
                print(f"Gemini called: {part.function_call.name}({dict(part.function_call.args)})")
            if part.function_response:
                print(f"Tool returned: {part.function_response.response}")

    print()
    print("=== Final answer ===")
    print(response.text)

    return response.text


if __name__ == "__main__":
    ask("Did Declan Rice play well in match_id 1?")
