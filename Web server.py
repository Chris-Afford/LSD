from fastapi import FastAPI, Request, Form, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlmodel import SQLModel, create_engine, Session, select, Field
from typing import Optional, Dict, List
from passlib.hash import bcrypt
from pydantic import BaseModel
from server import app, engine, Club  # Reuse existing models and FastAPI app
import secrets
import json
import uvicorn
from datetime import date
import os


# Setup
app = FastAPI()
templates = Jinja2Templates(directory="templates")
database_url = "sqlite:////data/database.db"
engine = create_engine(database_url, echo=True)
security = HTTPBasic()

# Models
class Club(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    username: str
    password_hash: str

class Venue(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    club_id: int

class Result(BaseModel):
    timestamp: str
    club_id: int
    venue_name: str
    status: str
    message1: str
    message2: str
    track_condition: str
    correct_weight: str
    raw_message: str

@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)

@app.post("/login")
def login(credentials: dict):
    username = credentials.get("username")
    password = credentials.get("password")

    with Session(engine) as session:
        club = session.exec(select(Club).where(Club.username == username)).first()
        if not club or not bcrypt.verify(password, club.password_hash):
            raise HTTPException(status_code=401, detail="Invalid login")

        venues = session.exec(select(Venue).where(Venue.club_id == club.id)).all()
        return {"club_id": club.id, "venues": [v.name for v in venues]}

@app.post("/submit/{club_id}")
def submit_result(club_id: int, result: Result):
    result_data = result.dict()
    filename = f"results_club_{club_id}.json"

    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump({}, f)

    with open(filename, "r") as f:
        existing_data = json.load(f)

    existing_data[result_data["venue_name"]] = result_data

    with open(filename, "w") as f:
        json.dump(existing_data, f, indent=2)

    return {"status": "ok"}

# Admin Login
ADMIN_USERNAME = "Felix"
ADMIN_PASSWORD = bcrypt.hash("1973")

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    if not secrets.compare_digest(credentials.username, ADMIN_USERNAME):
        raise HTTPException(status_code=401, detail="Invalid username")
    if not bcrypt.verify(credentials.password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid password")
    return credentials.username

# Admin Dashboard
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, username: str = Depends(verify_admin)):
    with Session(engine) as session:
        clubs = session.exec(select(Club)).all()
        venues = session.exec(select(Venue)).all()
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "clubs": clubs,
        "venues": venues
    })

@app.post("/admin/add_club", response_class=RedirectResponse)
def add_club(
    name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    user: str = Depends(verify_admin)
):
    hashed_pw = bcrypt.hash(password)
    with Session(engine) as session:
        club = Club(name=name, username=username, password_hash=hashed_pw)
        session.add(club)
        session.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/add_venue", response_class=RedirectResponse)
def add_venue(
    club_id: int = Form(...),
    venue_name: str = Form(...),
    user: str = Depends(verify_admin)
):
    with Session(engine) as session:
        venue = Venue(name=venue_name, club_id=club_id)
        session.add(venue)
        session.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/delete_venue")
async def delete_venue(request: Request):
    data = await request.json()
    venue_id = data.get("venue_id")

    with Session(engine) as session:
        venue = session.get(Venue, venue_id)
        if venue:
            session.delete(venue)
            session.commit()
    return {"status": "ok"}

@app.get("/admin/results/{club_id}", response_class=HTMLResponse)
def admin_results(request: Request, club_id: int, username: str = Depends(verify_admin)):
    filename = f"results_club_{club_id}.json"
    if not os.path.exists(filename):
        return templates.TemplateResponse("admin_results.html", {"request": request, "result": None})

    with open(filename, "r") as f:
        all_data = json.load(f)

    return templates.TemplateResponse("admin_results.html", {"request": request, "result": all_data})

# Day Pass Recording and View
class DayPass(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    venue_id: int
    date: str

def record_day_pass(venue_id: int):
    today = date.today().isoformat()
    with Session(engine) as session:
        exists = session.exec(
            select(DayPass).where(DayPass.venue_id == venue_id, DayPass.date == today)
        ).first()
        if not exists:
            session.add(DayPass(venue_id=venue_id, date=today))
            session.commit()

@app.get("/admin/daypasses/{club_id}", response_class=HTMLResponse)
def view_daypasses(request: Request, club_id: int, username: str = Depends(verify_admin)):
    with Session(engine) as session:
        venues = session.exec(select(Venue).where(Venue.club_id == club_id)).all()
        all_passes = []
        for v in venues:
            passes = session.exec(select(DayPass).where(DayPass.venue_id == v.id)).all()
            all_passes.append((v.name, passes))
    return templates.TemplateResponse("daypasses.html", {"request": request, "passes": all_passes})

# In-memory connection store
connections: Dict[int, List[WebSocket]] = {}

@app.websocket("/ws/{club_id}")
async def websocket_endpoint(websocket: WebSocket, club_id: int):
    await websocket.accept()
    if club_id not in connections:
        connections[club_id] = []
    connections[club_id].append(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep alive, ignore content
    except WebSocketDisconnect:
        connections[club_id].remove(websocket)
        if not connections[club_id]:
            del connections[club_id]

# Broadcast function
async def broadcast_result(club_id: int, result_data: dict):
    if club_id in connections:
        for ws in connections[club_id]:
            try:
                await ws.send_json(result_data)
            except Exception:
                connections[club_id].remove(ws)

# Update /submit route in main server to call broadcast_result
@app.post("/submit/{club_id}")
async def submit_result(club_id: int, result: dict):
    filename = f"results_club_{club_id}.json"

    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump({}, f)

    with open(filename, "r") as f:
        existing_data = json.load(f)

    existing_data[result["venue_name"]] = result

    with open(filename, "w") as f:
        json.dump(existing_data, f, indent=2)

    await broadcast_result(club_id, result)

    return {"status": "ok"}


