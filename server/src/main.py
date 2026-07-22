import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db import init_db, close_db
from routes import websocket, webhooks, extensions, configuration
from utils.chaster_api import close_chaster_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await close_db()
    await close_chaster_client()

app = FastAPI(lifespan=lifespan)

# Allowlist the known frontend origin only; "*" with credentials is invalid
# per the CORS spec (REVIEW.md #14).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONT_URL", "http://localhost:5173")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(websocket.router)
app.include_router(webhooks.chaster.router)
app.include_router(extensions.router)
app.include_router(configuration.router)

if __name__ == "__main__":
    import uvicorn
    print("WebSocket server listening on port 8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
