"""Resolves canonical/API-Football-style team names (e.g. "Manchester City", matching the
convention every other agent tool uses) to the offline training data's own naming
convention (football-data.co.uk style, e.g. "Man City" - see db/training_data/README.md).

Kept separate from src.scraping.name_matching.TEAM_ALIASES rather than added to it, even
though empirically that would be safe (TEAM_ALIASES is only consulted by match_team_name
after an exact-match check, and every offline short form here already exact-matches its own
FBref/API-Football alias where one exists in that dict) - this is a third, unrelated naming
convention, and TEAM_ALIASES is load-bearing for the live ingestion pipeline. No reason to
put a live-pipeline-critical dict at any risk, however small, for an offline-only concern.
"""

# Verified empirically against db/training_data/PL_last8seasons.csv's real HomeTeam/AwayTeam
# values, not guessed - only includes entries where the offline short form actually differs
# from the canonical name (most Premier League club names already match as-is).
OFFLINE_TEAM_ALIASES = {
    "Manchester City": "Man City",
    "Manchester United": "Man United",
    "Cardiff City": "Cardiff",
    "Huddersfield Town": "Huddersfield",
    "Ipswich Town": "Ipswich",
    "West Bromwich Albion": "West Brom",
    "AFC Bournemouth": "Bournemouth",
    # The dataset itself uses two different spellings across its own history (a real
    # inconsistency in the source data, not introduced here) - "Nottm Forest" for
    # 2022-08 to 2024-12, "Nott'm Forest" from 2024-12-26 onward. Mapping to the more
    # recent spelling matters for correctness: Elo/form/h2h lookups filter by exact team
    # name, so mapping to the older spelling would silently miss the team's most recent
    # matches when computing "current" features.
    "Nottingham Forest": "Nott'm Forest",
}
