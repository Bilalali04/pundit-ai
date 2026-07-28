import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

database_url = os.getenv("DATABASE_URL")

if not database_url:
    print("DATABASE_URL not set in .env")
else:
    engine = create_engine(database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Connection succeeded")
    except Exception as e:
        print(f"Connection failed: {type(e).__name__}")
