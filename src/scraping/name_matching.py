import logging
import unicodedata

logger = logging.getLogger(__name__)

# Characters Unicode NFKD decomposition does not resolve to a base letter,
# since they are distinct letters rather than a base letter + combining mark.
_CHAR_OVERRIDES = {
    "Ø": "O", "ø": "o",
    "ß": "ss",
    "Đ": "D", "đ": "d",
    "Ł": "L", "ł": "l",
    "Æ": "AE", "æ": "ae",
    "Œ": "OE", "œ": "oe",
}

# Same player, genuinely different display name across sources (nickname,
# alternate registered name) - not fixable by normalization alone.
# Add new pairs here as they're discovered via the unmatched-name logs below.
_ALIAS_PAIRS = [
    ("Sávio", "Savinho"),
    ("Nicolás González", "Nico González"),
]


def normalize_name(name: str) -> str:
    for char, replacement in _CHAR_OVERRIDES.items():
        name = name.replace(char, replacement)
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.strip().lower()


_ALIASES = {normalize_name(fbref_name): normalize_name(api_name) for fbref_name, api_name in _ALIAS_PAIRS}


def filter_active_players(api_players: list[dict]) -> dict[str, dict]:
    """Reduce API-Football's full-squad player list to those who actually played.

    api_players is the flattened list of player entries from the
    fixtures/players response (both teams combined). Returns a dict mapping
    player name to their stats entry, for players with minutes > 0.
    """
    active = {}
    for p in api_players:
        minutes = p["statistics"][0]["games"]["minutes"]
        if minutes and minutes > 0:
            active[p["player"]["name"]] = p
    return active


def match_player_name(fbref_name: str, active_api_players: dict[str, dict], match_id: str | None = None) -> str | None:
    """Match an FBref player name against API-Football's active (minutes > 0) player names.

    Returns the matching API-Football name, or None if no match was found
    (logged as a warning so it can be reviewed and added to _ALIAS_PAIRS).
    """
    if fbref_name in active_api_players:
        return fbref_name

    normalized_lookup = {normalize_name(name): name for name in active_api_players}
    normalized_fbref = normalize_name(fbref_name)

    if normalized_fbref in normalized_lookup:
        return normalized_lookup[normalized_fbref]

    aliased = _ALIASES.get(normalized_fbref)
    if aliased and aliased in normalized_lookup:
        return normalized_lookup[aliased]

    logger.warning("No name match found for player %r in match %s", fbref_name, match_id)
    return None


# Same club, genuinely different display name across sources (short form,
# historical suffix). Add new pairs here as they're discovered.
TEAM_ALIASES = {
    "Manchester Utd": "Manchester United",
    "Nottingham": "Nottingham Forest",
    "Leeds United": "Leeds",
    "Brighton & Hove Albion": "Brighton",
    "Newcastle United": "Newcastle",
    "Tottenham Hotspur": "Tottenham",
    "West Ham United": "West Ham",
    "Wolverhampton Wanderers": "Wolves",
}


def match_team_name(fbref_name: str, api_team_names, match_id: str | None = None) -> str | None:
    """Match an FBref team name against a collection of API-Football team names.

    Returns the matching API-Football name, or None if no match was found
    (logged as a warning so it can be reviewed and added to TEAM_ALIASES).
    """
    if fbref_name in api_team_names:
        return fbref_name

    normalized_lookup = {normalize_name(name): name for name in api_team_names}
    normalized_fbref = normalize_name(fbref_name)

    if normalized_fbref in normalized_lookup:
        return normalized_lookup[normalized_fbref]

    aliased = TEAM_ALIASES.get(fbref_name)
    if aliased and aliased in api_team_names:
        return aliased

    logger.warning("No name match found for team %r in match %s", fbref_name, match_id)
    return None
