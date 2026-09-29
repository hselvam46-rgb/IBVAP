"""
IBVAP Edge Server Application Entrypoint.
Unified FastAPI service hosting REST APIs, low-latency WebSocket video streams,
and the Operator Tactical Command Console.
"""

import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.database.db import init_db
from backend.api.routes import router as api_router
from backend.api.websocket import ws_router
from backend.core.config import DATA_DIR, BASE_DIR

app = FastAPI(
    title="IBVAP - Intelligent Border Vigilance & Analytics Platform",
    version="2.0-Edge",
    description="Edge-Native Military C4I Video Analytics for Indian Border Surveillance"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Mount Routers
app.include_router(api_router)
app.include_router(ws_router)

# Mount Static Asset Directories
frontend_dir = os.path.join(BASE_DIR, "frontend")
snapshots_dir = os.path.join(DATA_DIR, "snapshots")
evidence_dir = os.path.join(DATA_DIR, "evidence")

os.makedirs(frontend_dir, exist_ok=True)
os.makedirs(snapshots_dir, exist_ok=True)
os.makedirs(evidence_dir, exist_ok=True)

app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")
app.mount("/data/snapshots", StaticFiles(directory=snapshots_dir), name="snapshots")
app.mount("/data/evidence", StaticFiles(directory=evidence_dir), name="evidence")
app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dir, "assets")), name="assets")


@app.on_event("startup")
def on_startup():
    """Initialize database tables and default seed data on startup."""
    init_db()


@app.get("/")
def serve_index():
    """Serve the Tactical Command Console."""
    index_path = os.path.join(frontend_dir, "index.html")
    return FileResponse(index_path)


@app.get("/health")
def health_check():
    return {
        "status": "HEALTHY",
        "system": "IBVAP_BORDER_SURVEILLANCE_EDGE",
        "architecture": "EDGE_SINGLE_SERVICE",
        "node": "BOP_FEROZEPUR_SECTOR_88"
    }
