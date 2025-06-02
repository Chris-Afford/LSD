from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Dict
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import hashlib

app = FastAPI()

# Allow local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DATABASE SETUP ---
DATABASE_URL = "sqlite:///./scoreboard.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Venue(Base):
    __tablename__ = "venues"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    username = Column(String, unique=True)
    password_hash = Column(String)
    last_login = Column(DateTime, default=datetime.utcnow)

class ResultData(Base):
    __tablename__ = "results"
    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)
    message1 = Column(String)
    message2 = Column(String)
    track_condition = Column(String)
    correct_weight = Column(String)
    raw_message = Column(String)

Base.metadata.create_all(bind=engine)

# --- MODELS ---
class LoginRequest(BaseModel):
    username: str
    password: str

class ResultSubmission(BaseModel):
    timestamp: str
    venue_id: int
    status: str
    message1: str
    message2: str
    track_condition: str
    correct_weight: str
    raw_message: str

# --- HELPERS ---
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# --- API ROUTES ---
@app.post("/login")
def login(data: LoginRequest):
    db = SessionLocal()
    user = db.query(Venue).filter_by(username=data.username).first()
    if user and user.password_hash == hash_password(data.password):
        user.last_login = datetime.utcnow()
        db.commit()
        return {"venue_id": user.id, "venue_name": user.name}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/submit/{venue_id}")
def submit_results(venue_id: int, data: ResultSubmission):
    db = SessionLocal()
    venue = db.query(Venue).filter_by(id=venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    new_result = ResultData(
        venue_id=venue_id,
        timestamp=datetime.utcnow(),
        message1=data.message1,
        message2=data.message2,
        track_condition=data.track_condition,
        correct_weight=data.correct_weight,
        raw_message=data.raw_message
    )
    db.add(new_result)
    db.commit()
    return {"status": "ok"}

@app.get("/scoreboard/{venue_id}")
def get_latest_result(venue_id: int):
    db = SessionLocal()
    result = db.query(ResultData).filter_by(venue_id=venue_id).order_by(ResultData.timestamp.desc()).first()
    if not result:
        raise HTTPException(status_code=404, detail="No result found")
    return {
        "timestamp": result.timestamp.isoformat(),
        "message1": result.message1,
        "message2": result.message2,
        "track_condition": result.track_condition,
        "correct_weight": result.correct_weight,
        "raw_message": result.raw_message,
    }

# For adding test users manually (delete in production)
@app.post("/create_venue")
def create_venue(name: str, username: str, password: str):
    db = SessionLocal()
    if db.query(Venue).filter_by(username=username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    new_venue = Venue(
        name=name,
        username=username,
        password_hash=hash_password(password)
    )
    db.add(new_venue)
    db.commit()
    return {"status": "created", "venue_id": new_venue.id}
