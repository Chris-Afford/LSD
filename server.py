from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlmodel import SQLModel, create_engine, Session, select, Field
from typing import Optional
from passlib.hash import bcrypt
from pydantic import BaseModel
import secrets
import json
import uvicorn
from datetime import date

# Setup
app = FastAPI()
templates = Jinja2Templates(directory="templates")
database_url = "sqlite:////data/database.db"  # Use Render's persistent volume
engine = create_engine(database_url, echo=True)
security = HTTPBasic()

# Database Models
class Club(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    username: str
    password_hash: str

class Venue(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    club_id: int

class DayPass(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    venue_id: int
    date: str

class Result(BaseModel):
    timestamp: str
    venue_id: int
    status: str
    message1: str
    message2: str
    track_condition: str
    correct_weight: str
    raw_message: str

# Database Initialization
@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)

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

@app.get("/admin/results/{venue_id}", response_class=HTMLResponse)
def admin_results(request: Request, venue_id: int, username: str = Depends(verify_admin)):
    with open("results_store.json", "r") as f:
        all_data = json.load(f)
    result = all_data.get(str(venue_id))
    return templates.TemplateResponse("admin_results.html", {"request": request, "result": result})

# Day Pass Recording and View
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

# Dev run
if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
