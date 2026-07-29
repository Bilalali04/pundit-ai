from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class League(Base):
    __tablename__ = "leagues"

    league_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str | None] = mapped_column(String(100))
    tier: Mapped[int | None] = mapped_column(SmallInteger, server_default=text("1"))

    teams: Mapped[list["Team"]] = relationship(back_populates="league")
    matches: Mapped[list["Match"]] = relationship(back_populates="league")


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("name", "league_id"),)

    team_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    league_id: Mapped[int | None] = mapped_column(ForeignKey("leagues.league_id"))
    short_name: Mapped[str | None] = mapped_column(String(20))

    league: Mapped["League | None"] = relationship(back_populates="teams")
    players: Mapped[list["Player"]] = relationship(back_populates="team")
    home_matches: Mapped[list["Match"]] = relationship(
        back_populates="home_team", foreign_keys="Match.home_team_id"
    )
    away_matches: Mapped[list["Match"]] = relationship(
        back_populates="away_team", foreign_keys="Match.away_team_id"
    )


class Player(Base):
    __tablename__ = "players"

    player_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.team_id"))
    position: Mapped[str | None] = mapped_column(String(20))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(String(50))

    team: Mapped["Team | None"] = relationship(back_populates="players")
    match_stats: Mapped[list["PlayerMatchStats"]] = relationship(back_populates="player")
    match_events: Mapped[list["MatchEvent"]] = relationship(back_populates="player")
    availability: Mapped[list["PlayerAvailability"]] = relationship(back_populates="player")


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint("home_team_id <> away_team_id"),
        Index("idx_matches_date", "match_date"),
        Index("idx_matches_teams", "home_team_id", "away_team_id"),
    )

    match_id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int | None] = mapped_column(ForeignKey("leagues.league_id"))
    match_date: Mapped[date] = mapped_column(Date, nullable=False)
    home_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.team_id"))
    away_team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.team_id"))
    home_score: Mapped[int | None] = mapped_column(SmallInteger)
    away_score: Mapped[int | None] = mapped_column(SmallInteger)
    home_xg: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    away_xg: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    season: Mapped[str | None] = mapped_column(String(9))
    source: Mapped[str | None] = mapped_column(String(20))
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())

    league: Mapped["League | None"] = relationship(back_populates="matches")
    home_team: Mapped["Team | None"] = relationship(
        back_populates="home_matches", foreign_keys=[home_team_id]
    )
    away_team: Mapped["Team | None"] = relationship(
        back_populates="away_matches", foreign_keys=[away_team_id]
    )
    player_stats: Mapped[list["PlayerMatchStats"]] = relationship(back_populates="match")
    events: Mapped[list["MatchEvent"]] = relationship(back_populates="match")
    availability: Mapped[list["PlayerAvailability"]] = relationship(back_populates="match")
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="match")


class PlayerMatchStats(Base):
    __tablename__ = "player_match_stats"
    __table_args__ = (
        UniqueConstraint("match_id", "player_id"),
        Index("idx_pms_player", "player_id"),
        Index("idx_pms_match", "match_id"),
    )

    stat_id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.match_id"))
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.player_id"))
    minutes_played: Mapped[int | None] = mapped_column(SmallInteger)
    goals: Mapped[int | None] = mapped_column(SmallInteger, server_default=text("0"))
    assists: Mapped[int | None] = mapped_column(SmallInteger, server_default=text("0"))
    tackles: Mapped[int | None] = mapped_column(SmallInteger, server_default=text("0"))
    tackles_won: Mapped[int | None] = mapped_column(SmallInteger, server_default=text("0"))
    interceptions: Mapped[int | None] = mapped_column(SmallInteger, server_default=text("0"))
    passes_total: Mapped[int | None] = mapped_column(Integer)
    passes_completed: Mapped[int | None] = mapped_column(SmallInteger)
    duels_total: Mapped[int | None] = mapped_column(SmallInteger, server_default=text("0"))
    duels_won: Mapped[int | None] = mapped_column(SmallInteger, server_default=text("0"))
    key_passes: Mapped[int | None] = mapped_column(SmallInteger)
    shots_total: Mapped[int | None] = mapped_column(SmallInteger)
    shots_on_target: Mapped[int | None] = mapped_column(SmallInteger)
    dribbles_attempted: Mapped[int | None] = mapped_column(SmallInteger)
    dribbles_successful: Mapped[int | None] = mapped_column(SmallInteger)
    yellow_cards: Mapped[int | None] = mapped_column(SmallInteger, server_default=text("0"))
    red_cards: Mapped[int | None] = mapped_column(SmallInteger, server_default=text("0"))
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))

    match: Mapped["Match | None"] = relationship(back_populates="player_stats")
    player: Mapped["Player | None"] = relationship(back_populates="match_stats")


class MatchEvent(Base):
    __tablename__ = "match_events"
    __table_args__ = (Index("idx_events_match", "match_id"),)

    event_id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.match_id"))
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.player_id"))
    minute: Mapped[int | None] = mapped_column(SmallInteger)
    event_type: Mapped[str | None] = mapped_column(String(30))
    detail: Mapped[str | None] = mapped_column(Text)

    match: Mapped["Match | None"] = relationship(back_populates="events")
    player: Mapped["Player | None"] = relationship(back_populates="match_events")


class PlayerAvailability(Base):
    __tablename__ = "player_availability"
    __table_args__ = (Index("idx_availability_match", "match_id"),)

    availability_id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.player_id"))
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.match_id"))
    status: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)

    player: Mapped["Player | None"] = relationship(back_populates="availability")
    match: Mapped["Match | None"] = relationship(back_populates="availability")


class Prediction(Base):
    __tablename__ = "predictions"

    prediction_id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.match_id"))
    predicted_at: Mapped[datetime | None] = mapped_column(DateTime, server_default=func.now())
    home_win_prob: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    draw_prob: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    away_win_prob: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    model_version: Mapped[str | None] = mapped_column(String(20))

    match: Mapped["Match | None"] = relationship(back_populates="predictions")
