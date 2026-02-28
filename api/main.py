"""
api/main.py — FastAPI entry point for ExplainDeFi
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from core.config import config
from api.routes import router

app = FastAPI(
    title="ExplainDeFi API",
    description="AI-powered DeFi Transaction Failure Diagnosis",
    version="1.0.0",
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api")

# Serve the web frontend if the folder exists
web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
if os.path.exists(web_dir):
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(web_dir, "index.html"))

@app.on_event("startup")
async def startup_event():
    # Validate API keys on startup
    warnings = config.validate()
    for w in warnings:
        print(f"Startup Warning: {w}")
