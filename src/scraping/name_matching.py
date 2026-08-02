import logging
import re
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
    ("Valentín Castellanos", "Taty Castellanos"),
    ("Tino Livramento", "Valentino Livramento"),
    ("Joshua Acheampong", "Josh Acheampong"),
    ("Emi Buendía", "Emiliano Buendía"),
    ("Eddie Nketiah", "Edward Nketiah"),
]


def normalize_name(name: str) -> str:
    for char, replacement in _CHAR_OVERRIDES.items():
        name = name.replace(char, replacement)
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.strip().lower()


_ALIASES = {normalize_name(fbref_name): normalize_name(api_name) for fbref_name, api_name in _ALIAS_PAIRS}
_ALIASES_REVERSE = {api_name: fbref_name for fbref_name, api_name in _ALIASES.items()}


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

    # Checked in both directions since callers don't always pass an FBref-style name
    # first - ingest_match_events() passes an API-Football name first, for example.
    aliased = _ALIASES.get(normalized_fbref) or _ALIASES_REVERSE.get(normalized_fbref)
    if aliased and aliased in normalized_lookup:
        return normalized_lookup[aliased]

    logger.warning("No name match found for player %r in match %s", fbref_name, match_id)
    return None


_ABBREVIATED_NAME_RE = re.compile(r"^((?:[A-Za-zÀ-ÿ]\.\s*)+)(.+)$")


def match_abbreviated_name(abbreviated_name: str, full_names, match_id: str | None = None) -> str | None:
    """Match an API-Football abbreviated name like "E. Haaland" or "D. M. Wolfe" against
    known full names.

    Handles any number of leading initials (API-Football sometimes gives two, e.g. for a
    player with a two-part given name), matching on the FIRST initial only and comparing
    the surname portion against each candidate's trailing N tokens, where N is however
    many words the abbreviated form's own surname portion has. This correctly handles
    both compound surnames ("van Hecke") and candidates whose full name has extra given
    names before the real surname ("Jaydon Amauri Banel" matches "J. Banel" via just its
    last token, not "Amauri Banel").

    Each candidate is also checked against its alias (if any in _ALIAS_PAIRS), since a
    nickname's initial can differ from the formal name's initial (e.g. "T. Castellanos"
    for the nickname Taty, formal name Valentín) - matching only the candidate's own name
    would never catch that.

    full_names is an iterable of full names for the two rosters involved in the match
    (both teams combined, so ambiguity - two players sharing an initial + surname - can
    actually be detected rather than silently matching the wrong side).

    Returns the matching full name, or None if the input isn't in abbreviated form, no
    candidate matches, or more than one candidate matches (logged as a warning in the
    ambiguous case, so it can be reviewed rather than guessed).
    """
    match = _ABBREVIATED_NAME_RE.match(abbreviated_name.strip())
    if not match:
        return None

    initials_part, surname_part = match.groups()
    first_initial = normalize_name(initials_part.strip()[0])
    normalized_surname = normalize_name(surname_part.strip())
    surname_word_count = len(surname_part.strip().split())

    def variant_matches(name_variant: str) -> bool:
        tokens = name_variant.split()
        if len(tokens) <= surname_word_count:
            return False
        variant_initial = normalize_name(tokens[0])[:1]
        variant_surname = normalize_name(" ".join(tokens[-surname_word_count:]))
        return variant_initial == first_initial and variant_surname == normalized_surname

    candidates = []
    for full_name in full_names:
        normalized_full = normalize_name(full_name)
        aliased = _ALIASES.get(normalized_full) or _ALIASES_REVERSE.get(normalized_full)
        if variant_matches(full_name) or (aliased and variant_matches(aliased)):
            candidates.append(full_name)

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) > 1:
        logger.warning(
            "Ambiguous abbreviated name %r in match %s - matches multiple players: %s",
            abbreviated_name,
            match_id,
            candidates,
        )
        return None

    logger.warning("No name match found for abbreviated name %r in match %s", abbreviated_name, match_id)
    return None


def match_bare_first_name(name: str, full_names, match_id: str | None = None) -> str | None:
    """Match a bare single-token name (e.g. "Nico") against known full names by first name.

    full_names should be scoped to ONE team's roster, not both teams pooled - a bare
    first name is likely to collide across two 25+ player squads (e.g. "Nico" matches
    both "Nico O'Reilly" and "Nico Gonzalez" if both rosters are checked at once), so
    the caller is expected to resolve the event's team first and pass only that team's
    players here.

    Returns the matching full name, or None if no candidate matches or more than one
    does (logged as a warning in the ambiguous case, so it can be reviewed rather than
    guessed).
    """
    normalized_name = normalize_name(name.strip())

    candidates = []
    for full_name in full_names:
        first_token = full_name.split()[0]
        if normalize_name(first_token) == normalized_name:
            candidates.append(full_name)

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) > 1:
        logger.warning(
            "Ambiguous bare first name %r in match %s - matches multiple players: %s",
            name,
            match_id,
            candidates,
        )
        return None

    logger.warning("No name match found for bare first name %r in match %s", name, match_id)
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
    "Man City": "Manchester City",
    "Man Utd": "Manchester United",
    "Spurs": "Tottenham",
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
