# database.py
from sqlmodel import create_engine

# Update this path if you're not using Render's /data volume
DATABASE_URL = "sqlite:////data/database.db"
engine = create_engine(DATABASE_URL, echo=True)
