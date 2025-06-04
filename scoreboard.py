# scoreboard.py
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from passlib.hash import bcrypt
from starlette.middleware.sessions import SessionMiddleware

from database import engine
from models import Club, Venue

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Scoreboard Login Page
@router.get("/scoreboard/login", response_class=HTMLResponse)
def scoreboard_login_page(request: Request):
    return templates.TemplateResponse("scoreboard_login.html", {"request": request})

# Handle Login Submission
@router.post("/scoreboard/login")
def scoreboard_login(request: Request, username: str = Form(...), password: str = Form(...)):
    with Session(engine) as session:
        club = session.exec(select(Club).where(Club.username == username)).first()
        if not club or not bcrypt.verify(password, club.password_hash):
            return templates.TemplateResponse("scoreboard_login.html", {
                "request": request,
                "error": "Invalid login"
            })
        request.session["club_id"] = club.id
        return RedirectResponse(url=f"/scoreboard/view", status_code=302)

# Scoreboard Display Page
@router.get("/scoreboard/view", response_class=HTMLResponse)
def scoreboard_view(request: Request):
    club_id = request.session.get("club_id")
    if not club_id:
        return RedirectResponse(url="/scoreboard/login")

    with Session(engine) as session:
        venues = session.exec(select(Venue).where(Venue.club_id == club_id)).all()
        venue_names = [v.name for v in venues]

    return templates.TemplateResponse("scoreboard_view.html", {
        "request": request,
        "club_id": club_id,
        "venue_names": venue_names
    })

def register_scoreboard_routes(app):
    app.include_router(router)
    app.add_middleware(SessionMiddleware, secret_key="your-secret-key")
