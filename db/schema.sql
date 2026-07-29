-- ============================================================
-- Pundit AI - PostgreSQL Schema
-- ============================================================
-- Design notes:
-- - Normalized relational structure: leagues -> teams -> players,
--   and matches -> player_match_stats, so the same player/team
--   rows are reused across many matches rather than duplicated.
-- - player_match_stats is the core table the agent queries for
--   "how did X play" questions, and the core training table for
--   XGBoost feature engineering.
-- - match_events supports the "flag a mistake that led to a goal"
--   feature by storing timestamped events per match.
-- - injuries/availability feeds V2 prediction (is a key player out).
-- - predictions stores the model's own outputs for later evaluation
--   (did the model's prediction match reality - useful for retraining
--   and for showing accuracy over time in a demo).
-- ============================================================

CREATE TABLE leagues (
    league_id       SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    country         VARCHAR(100),
    tier            SMALLINT DEFAULT 1          -- 1 = top division, etc.
);

CREATE TABLE teams (
    team_id         SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    league_id       INTEGER REFERENCES leagues(league_id),
    short_name      VARCHAR(20),
    UNIQUE (name, league_id)
);

CREATE TABLE players (
    player_id       SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    team_id         INTEGER REFERENCES teams(team_id),
    position        VARCHAR(20),                -- GK, CB, FB, CM, WM, ST, etc.
    date_of_birth   DATE,
    nationality     VARCHAR(50)
);

CREATE TABLE matches (
    match_id        SERIAL PRIMARY KEY,
    league_id       INTEGER REFERENCES leagues(league_id),
    match_date      DATE NOT NULL,
    home_team_id    INTEGER REFERENCES teams(team_id),
    away_team_id    INTEGER REFERENCES teams(team_id),
    home_score      SMALLINT,
    away_score      SMALLINT,
    home_xg         NUMERIC(4,2),                -- team-level expected goals, from API-Football
    away_xg         NUMERIC(4,2),
    season          VARCHAR(9),                  -- e.g. '2025-2026'
    source          VARCHAR(20),                  -- 'fbref', 'understat', 'api-football'
    scraped_at      TIMESTAMP DEFAULT NOW(),
    CHECK (home_team_id <> away_team_id)
);

-- One row per player, per match: the core "how did X play" table
CREATE TABLE player_match_stats (
    stat_id         SERIAL PRIMARY KEY,
    match_id        INTEGER REFERENCES matches(match_id),
    player_id       INTEGER REFERENCES players(player_id),
    minutes_played  SMALLINT,
    goals           SMALLINT DEFAULT 0,
    assists         SMALLINT DEFAULT 0,
    tackles         SMALLINT DEFAULT 0,
    tackles_won     SMALLINT DEFAULT 0,
    interceptions   SMALLINT DEFAULT 0,
    crosses         SMALLINT DEFAULT 0,
    passes_total    INTEGER,
    passes_completed SMALLINT,
    duels_total     SMALLINT DEFAULT 0,
    duels_won       SMALLINT DEFAULT 0,
    key_passes      SMALLINT,
    shots_total     SMALLINT,
    shots_on_target SMALLINT,
    dribbles_attempted   SMALLINT,
    dribbles_successful  SMALLINT,
    yellow_cards    SMALLINT DEFAULT 0,
    red_cards       SMALLINT DEFAULT 0,
    rating          NUMERIC(3,1),                 -- if source provides one
    UNIQUE (match_id, player_id)
);

-- Timestamped in-match events - supports goal/error cross-referencing
CREATE TABLE match_events (
    event_id        SERIAL PRIMARY KEY,
    match_id        INTEGER REFERENCES matches(match_id),
    player_id       INTEGER REFERENCES players(player_id),
    minute          SMALLINT,
    event_type      VARCHAR(30),                  -- 'goal', 'card', 'substitution', 'own_goal', 'error'
    detail          TEXT                           -- free text, e.g. 'lost possession leading to goal'
);

-- Player availability - feeds V2 prediction (missing key players)
CREATE TABLE player_availability (
    availability_id SERIAL PRIMARY KEY,
    player_id       INTEGER REFERENCES players(player_id),
    match_id        INTEGER REFERENCES matches(match_id),
    status          VARCHAR(20),                  -- 'injured', 'suspended', 'available'
    note            TEXT
);

-- Stores the model's own predictions, for tracking accuracy over time
CREATE TABLE predictions (
    prediction_id   SERIAL PRIMARY KEY,
    match_id        INTEGER REFERENCES matches(match_id),
    predicted_at    TIMESTAMP DEFAULT NOW(),
    home_win_prob   NUMERIC(4,3),
    draw_prob       NUMERIC(4,3),
    away_win_prob   NUMERIC(4,3),
    model_version   VARCHAR(20)
);

-- ============================================================
-- Indexes for the query patterns the agent will actually run
-- ============================================================
CREATE INDEX idx_pms_player ON player_match_stats(player_id);
CREATE INDEX idx_pms_match ON player_match_stats(match_id);
CREATE INDEX idx_matches_date ON matches(match_date);
CREATE INDEX idx_matches_teams ON matches(home_team_id, away_team_id);
CREATE INDEX idx_events_match ON match_events(match_id);
CREATE INDEX idx_availability_match ON player_availability(match_id);

-- ============================================================
-- Example queries the agent's tools would run
-- ============================================================

-- "Did Marquinhos play well yesterday?" -> get his stat line + season baseline
-- SELECT * FROM player_match_stats pms
-- JOIN matches m ON pms.match_id = m.match_id
-- JOIN players p ON pms.player_id = p.player_id
-- WHERE p.name = 'Marquinhos' AND m.match_date = '2026-07-20';

-- Season baseline for context ("above/below his norm")
-- SELECT AVG(tackles), AVG(passes_total), AVG(rating)
-- FROM player_match_stats pms
-- JOIN matches m ON pms.match_id = m.match_id
-- WHERE pms.player_id = <id> AND m.season = '2025-2026';

-- Head-to-head history for V2 prediction
-- SELECT * FROM matches
-- WHERE (home_team_id = <a> AND away_team_id = <b>)
--    OR (home_team_id = <b> AND away_team_id = <a>)
-- ORDER BY match_date DESC;
