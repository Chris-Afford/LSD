# routes.py
from fastapi import Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.routing import APIRouter
from sqlmodel import Session, select
from passlib.hash import bcrypt
import secrets
import os
import json
from datetime import date

from database import engine
from models import Club, Venue, Result

router = APIRouter()

ADMIN_USERNAME = "Felix"
ADMIN_PASSWORD = bcrypt.hash("1973")

def verify_admin(credentials: HTTPBasicCredentials = Depends(HTTPBasic())):
    if not secrets.compare_digest(credentials.username, ADMIN_USERNAME):
        raise HTTPException(status_code=401, detail="Invalid username")
    if not bcrypt.verify(credentials.password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid password")
    return credentials.username

@router.post("/login")
def login(credentials: dict):
    username = credentials.get("username")
    password = credentials.get("password")

    with Session(engine) as session:
        club = session.exec(select(Club).where(Club.username == username)).first()
        if not club or not bcrypt.verify(password, club.password_hash):
            raise HTTPException(status_code=401, detail="Invalid login")

        venues = session.exec(select(Venue).where(Venue.club_id == club.id)).all()
        return {"club_id": club.id, "venues": [v.name for v in venues]}

@router.post("/submit/{club_id}")
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

def register_routes(app):
    app.include_router(router)
