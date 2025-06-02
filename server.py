from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

app = FastAPI()

# Allow CORS for all (you can lock this down later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for result data per venue
venues = {}  # Example: { "venue123": {"data": ..., "clients": [...]} }

@app.post("/submit/{venue_id}")
async def submit_data(venue_id: str, payload: dict):
    venues.setdefault(venue_id, {"data": {}, "clients": []})
    venues[venue_id]["data"] = {
        **payload,
        "timestamp": datetime.now().isoformat()
    }

    # Push update to any connected clients
    for client in venues[venue_id]["clients"]:
        try:
            await client.send_json(venues[venue_id]["data"])
        except:
            pass
    return {"status": "ok"}

@app.websocket("/ws/{venue_id}")
async def websocket_endpoint(websocket: WebSocket, venue_id: str):
    await websocket.accept()
    venues.setdefault(venue_id, {"data": {}, "clients": []})
    venues[venue_id]["clients"].append(websocket)

    try:
        # On connect, send current data
        if venues[venue_id]["data"]:
            await websocket.send_json(venues[venue_id]["data"])
        while True:
            await websocket.receive_text()  # Keep connection open
    except:
        pass
    finally:
        venues[venue_id]["clients"].remove(websocket)
