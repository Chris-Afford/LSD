# scoreboard.py
from fastapi import APIRouter, Request, Form, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware
from passlib.hash import bcrypt
from starlette.websockets import WebSocketState
import secrets
import os
import json
from datetime import datetime

from database import engine
from models import Club

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Store WebSocket connections for scoreboards
scoreboard_connections = {}

# Scoreboard login page
@router.get("/scoreboard", response_class=HTMLResponse)
def scoreboard_login_page(request: Request):
    return templates.TemplateResponse("scoreboard_login.html", {"request": request})

# Scoreboard login handler
@router.post("/scoreboard/login")
def scoreboard_login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    remember: bool = Form(False)
):
    with Session(engine) as session:
        club = session.exec(select(Club).where(Club.username == username)).first()
        if not club or not bcrypt.verify(password, club.password_hash):
            raise HTTPException(status_code=401, detail="Invalid login")

        request.session["club_id"] = club.id
        if remember:
            request.session["remember"] = True

      # Redirect to the scoreboard view page with the club_id in the query
        return RedirectResponse(
            url=f"/scoreboard/view?club_id={club.id}", status_code=302)

# Scoreboard view page
@router.get("/scoreboard/view", response_class=HTMLResponse)
def scoreboard_view(request: Request):
    club_id = request.session.get("club_id")
    if not club_id:
        return RedirectResponse(url="/scoreboard")

    filename = f"results_club_{club_id}.json"
    result = {}
    if os.path.exists(filename):
        with open(filename, "r") as f:
            all_results = json.load(f)

        if isinstance(all_results, dict) and all_results:
            latest_result = None
            latest_ts = None
            for r in all_results.values():
                ts_str = r.get("timestamp")
                try:
                    ts = datetime.fromisoformat(ts_str)
                except Exception:
                    ts = None
                if latest_ts is None or (ts and ts > latest_ts):
                    latest_ts = ts
                    latest_result = r
            if latest_result:
                result = latest_result

    return templates.TemplateResponse("scoreboard_display.html", {"request": request, "club_id": club_id, "result": result})

# WebSocket for scoreboard
@router.websocket("/scoreboard/ws/{club_id}")
async def scoreboard_ws(websocket: WebSocket, club_id: int):
    await websocket.accept()
    if club_id not in scoreboard_connections:
        scoreboard_connections[club_id] = []
    scoreboard_connections[club_id].append(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive only
    except WebSocketDisconnect:
        scoreboard_connections[club_id].remove(websocket)

# External broadcast function (to be imported where needed)
async def broadcast_to_scoreboard(club_id: int, result_data: dict):
    if club_id in scoreboard_connections:
        for ws in scoreboard_connections[club_id]:
            try:
                await ws.send_json(result_data)
            except:
                continue

# Register scoreboard routes
def register_scoreboard(app):
    app.include_router(router)


async def broadcast_scoreboard(club_id: int, data: dict):
    """Send data to all connected scoreboards for the given club."""
    if club_id in scoreboard_connections:
        disconnected = []
        for ws in scoreboard_connections[club_id]:
            if ws.application_state == WebSocketState.CONNECTED:
                await ws.send_json(data)
            else:
                disconnected.append(ws)
        for ws in disconnected:
            scoreboard_connections[club_id].remove(ws)
