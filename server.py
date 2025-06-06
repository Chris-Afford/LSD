# main.py
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from sqlmodel import SQLModel
from database import engine
from routes import register_routes
from scoreboard import router as scoreboard_router
from scoreboard import register_scoreboard
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles


app = FastAPI()
templates = Jinja2Templates(directory="templates")



app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(scoreboard_router, prefix="/scoreboard")
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")

@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)
    # Ensure new columns exist for older databases
    with engine.begin() as conn:
        info = conn.exec_driver_sql("PRAGMA table_info(daypass)").fetchall()
        cols = [row[1] for row in info]
        if "club_name" not in cols:
            conn.exec_driver_sql("ALTER TABLE daypass ADD COLUMN club_name TEXT")


register_routes(app)
register_scoreboard(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
