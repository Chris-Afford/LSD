from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import SQLModel, create_engine, Session, select, Field
from typing import Optional
import uvicorn

# Models
from pydantic import BaseModel

class Venue(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str
    password: str
    venue_id: int

class Result(BaseModel):
    timestamp: str
    venue_id: int
    status: str
    message1: str
    message2: str
    track_condition: str
    correct_weight: str
    raw_message: str

# App and DB setup
app = FastAPI()
templates = Jinja2Templates(directory="templates")
database_url = "sqlite:///./database.db"
engine = create_engine(database_url, echo=True)

@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)

# Admin panel
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    with Session(engine) as session:
        venues = session.exec(select(Venue)).all()
    return templates.TemplateResponse("admin_dashboard.html", {"request": request, "venues": venues})

@app.post("/admin/add", response_class=RedirectResponse)
def add_venue_and_user(
    name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...)
):
    with Session(engine) as session:
        venue = Venue(name=name)
        session.add(venue)
        session.commit()
        session.refresh(venue)

        user = User(username=username, password=password, venue_id=venue.id)
        session.add(user)
        session.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.get("/admin/results/{venue_id}", response_class=HTMLResponse)
def admin_results(request: Request, venue_id: int):
    with open("results_store.json", "r") as f:
        all_data = json.load(f)
    result = all_data.get(str(venue_id))
    return templates.TemplateResponse("admin_results.html", {"request": request, "result": result})

# For dev testing
if __name__ == "__main__":
    uvicorn.run("admin_panel_backend:app", host="0.0.0.0", port=8000, reload=True)
