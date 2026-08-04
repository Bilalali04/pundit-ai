# Training data (offline, not part of the live pipeline)

This directory holds static CSV data pulled for V2 (XGBoost match-outcome prediction)
experimentation. It is **not** ingested into the live PostgreSQL database and has no
relationship to `src/ingestion/`, `db/schema.sql`, or the Airflow DAGs - those all populate
the live Postgres tables from FBref/API-Football and are the source of truth for the agent.
This is separate, offline data for training/exploring the V2 model only.

## Source

Both files are taken as-is from
[xgabora/Club-Football-Match-Data-2000-2025](https://github.com/xgabora/Club-Football-Match-Data-2000-2025),
which itself sources match data from [Football-Data.co.uk](https://www.football-data.co.uk/)
and Elo ratings from [ClubElo](https://www.clubelo.com/). Downloaded 2026-08-04.

- **`PL_last8seasons.csv`** - a subset of that repo's `Matches.csv` (230,557 rows, 42 leagues,
  2000/01-2024/25), filtered to `Division == 'E0'` (Premier League) and matches from
  2017-07-01 onward (the last ~8 seasons). 3,040 rows, same 48 columns as the source file.
- **`EloRatings.csv`** - the source repo's Elo ratings file, copied in full (245,033 rows,
  ~500 European clubs, twice-monthly snapshots). Columns are `date`, `club`, `country`, `elo`
  (lowercase in the actual file - the source repo's README documents them capitalized, which
  doesn't match the real CSV header).

## Important caveat: the `C_*` columns are not raw data

`PL_last8seasons.csv` includes six columns - `C_LTH`, `C_LTA`, `C_VHD`, `C_VAD`, `C_HTB`,
`C_PHB` - that look like match statistics but are **not**. They're match-cluster membership
probabilities computed by the source dataset's author (e.g. `C_VHD` = likelihood a match
falls into a "Visibly Home Dominated" cluster), derived from the other columns via some
unpublished clustering method on their end. Treat them as a third party's derived feature,
not ground truth about the match - don't feed them into a model as if they were an
independent signal, and don't trust them more than you'd trust any other black-box feature
from an external source.

## Other things worth knowing before using this for V2

- **No player-level data.** Everything here is team-aggregate (shots, fouls, cards as team
  totals). Irrelevant to V1's player-performance-judgment use case; this is purely for V2's
  match-outcome prediction.
- **No xG.** Confirmed absent - the source README explicitly notes this isn't included.
- Heavy on betting-odds columns (Bet365 + max-of-17-bookmakers odds, Asian handicap,
  over/under 2.5). Useful as market-implied-probability features, but worth deciding
  deliberately whether to use them rather than including them by default.
- Data is sparse in older seasons (e.g. `MatchTime` is often null pre-2018) - the source
  README itself warns the table is "highly incomplete due to differences in statistics
  provided by each league."
