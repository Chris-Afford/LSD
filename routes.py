# routes.py
from fastapi import Request, Form, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from scoreboard import broadcast_scoreboard
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.routing import APIRouter
from sqlmodel import Session, select
from passlib.hash import bcrypt
import secrets
import os
import json
from datetime import date, datetime, timedelta

from database import engine
from models import Club, Venue, Result, DayPass  # Ensure DayPass exists in models.py
from fastapi.templating import Jinja2Templates
from fastapi import Query
import re

router = APIRouter()
templates = Jinja2Templates(directory="templates")

ADMIN_USERNAME = "Felix"
ADMIN_PASSWORD = bcrypt.hash("1973")

# Dictionary to manage connected websocket clients per club
websocket_connections = {}

# Admin verification
def verify_admin(credentials: HTTPBasicCredentials = Depends(HTTPBasic())):
    if not secrets.compare_digest(credentials.username, ADMIN_USERNAME):
        raise HTTPException(status_code=401, detail="Invalid username")
    if not bcrypt.verify(credentials.password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid password")
    return credentials.username

# User login
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


def parse_raw_message(raw: str):
    race_no = None
    runners = []
    message1 = None

    if not raw:
        return race_no, runners, message1

    # Normalize control characters and timestamps
    raw = raw.replace("\x02", "").replace("\x05", "").strip()
    raw = re.sub(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\s*", "", raw)

    # Message-only packet
    if not "Race:" in raw and raw.endswith("123"):  # basic check
        message1 = raw.strip()
        return None, [], message1

    # Race results parsing
    match = re.search(r"(Race:\s*\d+.*)", raw, re.DOTALL)
    if match:
        raw = match.group(1)
    else:
        return None, [], None

    clean = raw.replace("\r", "").replace("\n", " ")

    # Extract race number
    race_match = re.search(r"Race:\s*(\d+)", clean)
    if race_match:
        race_no = race_match.group(1)

    # Match full entries with valid time (like 1:18.69)
    entries = re.findall(r"Place:(\d+)\s+HorseID:(\d+)\s+Time:(\d+:\d+\.\d+)", clean)

    if entries:
        for place, horse_id, time in entries:
            runners.append(f"{horse_id} - {time}")
    else:
        # Detect "blank board" with no times and clear runners + message
        if re.search(r"Place:\s+HorseID:\d+\s+Time:\s*", clean):
            runners = []
            message1 = ""  # Clear Margins

    return race_no, runners, message1



# Record day pass
def record_day_pass(club_id: int):
    now = datetime.utcnow()
    with Session(engine) as session:
        recent = session.exec(
            select(DayPass)
            .where(DayPass.club_id == club_id)
            .order_by(DayPass.timestamp.desc())
        ).first()

        if not recent or now - recent.timestamp > timedelta(hours=24):
            club = session.get(Club, club_id)
            club_name = club.name if club else ""
            session.add(DayPass(club_id=club_id, club_name=club_name, timestamp=now))
            session.commit()

@router.post("/submit/{club_id}")
async def submit_result(club_id: int, result: Result):
    result_data = result.dict()
    race_num, runners, message1 = parse_raw_message(result_data.get("raw_message", ""))

    filename = f"results_club_{club_id}.json"

    # Load existing data
    if os.path.exists(filename):
        with open(filename, "r") as f:
            existing_data = json.load(f)
    else:
        existing_data = {}

    venue_name = result_data.get("venue_name", "Venue Name")
    previous_data = existing_data.get(venue_name, {})

    # Build updated record using existing values where needed
    updated_result = {
        "race_no": race_num or previous_data.get("race_no", ""),
        "runners": runners if runners else previous_data.get("runners", []),
        "correct_weight": "No",  # always reset unless overridden
        "track_condition": result_data.get("track_condition", previous_data.get("track_condition", "Good 4")),
        "venue_name": venue_name,
        "message1": message1 if message1 is not None else previous_data.get("message1", ""),
        "message2": result_data.get("message2", previous_data.get("message2", ""))
    }

    existing_data[venue_name] = updated_result

    with open(filename, "w") as f:
        json.dump(existing_data, f, indent=2)

    record_day_pass(club_id)

    if club_id in websocket_connections:
        for connection in websocket_connections[club_id]:
            try:
                await connection.send_json(updated_result)
            except:
                continue

    await broadcast_scoreboard(club_id, updated_result)

    return {"status": "ok"}


    # Also broadcast to connected scoreboard displays
    await broadcast_scoreboard(club_id, result_data)

    return {"status": "ok"}

# WebSocket endpoint
@router.websocket("/ws/{club_id}")
async def websocket_endpoint(websocket: WebSocket, club_id: int):
    await websocket.accept()
    if club_id not in websocket_connections:
        websocket_connections[club_id] = []
    websocket_connections[club_id].append(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_connections[club_id].remove(websocket)

# Admin dashboard
@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, username: str = Depends(verify_admin)):
    with Session(engine) as session:
        clubs = session.exec(select(Club)).all()
        venues = session.exec(select(Venue)).all()
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "clubs": clubs,
        "venues": venues
    })

#Default Page
def register_routes(app):
    @app.get("/", include_in_schema=False)
    def root_redirect():
        return RedirectResponse(url="/scoreboard")

@router.get("/admin/daypass_dashboard", response_class=HTMLResponse)
def daypass_dashboard(request: Request, username: str = Depends(verify_admin)):
    with Session(engine) as session:
        clubs = session.exec(select(Club)).all()
    return templates.TemplateResponse("daypass_dashboard.html", {"request": request, "clubs": clubs})

@router.get("/admin/daypass_data")
def get_daypass_data(club_id: int = Query(...)):
    with Session(engine) as session:
        logs = session.exec(
            select(DayPass).where(DayPass.club_id == club_id).order_by(DayPass.timestamp.desc())
        ).all()
        now = datetime.utcnow()
        month_total = sum(1 for p in logs if p.timestamp.month == now.month and p.timestamp.year == now.year)
        all_time_total = len(logs)
        last_30 = [
            {
                "club": p.club_name,
                "timestamp": p.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for p in logs[:30]
        ]
    return {
        "all_time": all_time_total,
        "this_month": month_total,
        "recent_logs": last_30
    }

@router.get("/admin/daypass_export")
def export_daypasses(club_id: int = Query(...), year: int = Query(...), month: int = Query(...)):
    with Session(engine) as session:
        logs = session.exec(
            select(DayPass).where(
                DayPass.club_id == club_id,
                DayPass.timestamp.month == month,
                DayPass.timestamp.year == year
            ).order_by(DayPass.timestamp.asc())
        ).all()
    lines = [
        f"{p.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - {p.club_name}"
        for p in logs
    ]
    export_file = f"export_daypasses_{club_id}_{year}_{month}.txt"
    with open(export_file, "w") as f:
        f.write("\n".join(lines))
    return FileResponse(export_file, filename=export_file, media_type="text/plain")

@router.post("/admin/add_club", response_class=RedirectResponse)
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

@router.post("/admin/add_venue", response_class=RedirectResponse)
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

@router.post("/admin/delete_venue")
async def delete_venue(request: Request):
    data = await request.json()
    venue_id = data.get("venue_id")

    with Session(engine) as session:
        venue = session.get(Venue, venue_id)
        if venue:
            club_id = venue.club_id
            session.delete(venue)
            session.commit()
            # Notify connected scoreboards to refresh venue list
            await broadcast_scoreboard(club_id, {"action": "delete_venue", "venue_id": venue_id})
    return {"status": "ok"}

@router.get("/admin/results/{club_id}", response_class=HTMLResponse)
def admin_results(request: Request, club_id: int, username: str = Depends(verify_admin)):
    filename = f"results_club_{club_id}.json"
    if not os.path.exists(filename):
        return templates.TemplateResponse("admin_results.html", {"request": request, "result": None})

    with open(filename, "r") as f:
        all_data = json.load(f)

    return templates.TemplateResponse("admin_results.html", {"request": request, "result": all_data})

def register_routes(app):
    app.include_router(router)
