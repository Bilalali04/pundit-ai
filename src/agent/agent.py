import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.agent.tools import (
    find_match,
    get_match_events,
    get_player_match_stats,
    get_player_season_baseline,
    get_position_expectations,
    get_team_matches,
    search_web,
)

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
    "versa - judge the rate, not just the raw number.\n\n"
    "When you use find_match to look up a match_id from team names and it returns "
    "'multiple_matches', do NOT pick one automatically. Stop and ask the user which specific "
    "match they meant, listing each candidate's date and score so they can choose - only call "
    "get_player_match_stats, get_match_events, or any other match-specific tool once you know "
    "the exact match_id.\n\n"
    "When a question is about a team's pattern, tendency, or record over the season (e.g. "
    "disciplinary record, recent form) rather than one specific match, call get_team_matches "
    "with a reasonable limit (10-15 recent matches) rather than pulling the full season - a "
    "recent sample is enough to characterize a trend and is far cheaper than checking every "
    "match. Only omit the limit (full season) if the user specifically asks for full-season or "
    "historical analysis.\n\n"
    "search_web is strictly for information that is genuinely outside the database's scope by "
    "nature - injury news, transfer rumors/news, contract situations, manager/club news, or "
    "other current-events football news that isn't a match performance stat. It is NOT a "
    "fallback for match/player questions the database tools simply failed to find (e.g. a "
    "typo'd player name, an unresolved match) - if a database tool returns no result, ask the "
    "user to clarify or correct the name/details rather than falling back to search_web. Never "
    "use search_web for anything the database tools are designed to answer (match stats, "
    "season stats, match events, team patterns), even if a specific query happens to fail. In "
    "your final answer, always clearly distinguish web-search-derived information from "
    "verified database stats (e.g. 'per a recent news report...' rather than stating it as "
    "fact), and summarize/paraphrase search findings in your own words rather than quoting "
    "them directly."
)


def ask(question: str) -> str:
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=question,
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
            ],
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
