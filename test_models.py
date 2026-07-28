from src.db.connection import SessionLocal
from src.db.models import Team

session = SessionLocal()

try:
    team = Team(name="Test FC", league_id=None)
    session.add(team)
    session.commit()
    print(f"Inserted: id={team.team_id}, name={team.name}, league_id={team.league_id}")

    fetched = session.query(Team).filter_by(name="Test FC").first()
    print(f"Read back: id={fetched.team_id}, name={fetched.name}, league_id={fetched.league_id}")

    session.delete(fetched)
    session.commit()

    gone = session.query(Team).filter_by(name="Test FC").first()
    print(f"After delete, query result: {gone}")
finally:
    session.close()
