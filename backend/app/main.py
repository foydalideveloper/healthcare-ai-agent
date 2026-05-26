"""Healthcare AI Agent - FastAPI Application Entry Point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.api import health, users, biometric, activity_events, health_level, simulation, dashboard, db_diagram, food_lookup, hrt_drilldown, lifelog, lifelog_chat, lifelog_reanalyze

settings = get_settings()

app = FastAPI(
    title="Healthcare AI Agent API",
    description="Generative AI-Based Autonomous Healthcare System - Triple-H Co., Ltd.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS - allow frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",       # Next.js dev
        "http://localhost:19006",      # React Native web
        "https://*.vercel.app",        # Vercel deployments
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router)
app.include_router(users.router, prefix="/api/v1")
app.include_router(biometric.router, prefix="/api/v1")
app.include_router(activity_events.router, prefix="/api/v1")
app.include_router(health_level.router, prefix="/api/v1")
app.include_router(simulation.router, prefix="/api/v1")
app.include_router(dashboard.router)
app.include_router(db_diagram.router)
app.include_router(food_lookup.router, prefix="/api/v1")
app.include_router(hrt_drilldown.router, prefix="/api/v1")
app.include_router(lifelog.router, prefix="/api/v1")
app.include_router(lifelog_chat.router, prefix="/api/v1")
app.include_router(lifelog_reanalyze.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "service": "Healthcare AI Agent",
        "version": "0.1.0",
        "patent": "10-2025-0145274",
        "docs": "/docs",
    }
