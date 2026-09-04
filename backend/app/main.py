"""FastAPI application entry point: app creation, CORS, and router registration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    analysis,
    auth,
    chats,
    health,
    messages,
    outputs,
    profile,
    tracker,
)
from app.core.config import settings

app = FastAPI(
    title="Applify API",
    description="Backend for Applify, a job application co-pilot.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GET /health is the only unprotected route; everything below it depends on
# get_current_user.
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(chats.router)
app.include_router(messages.router)
app.include_router(analysis.router)
app.include_router(outputs.router)
app.include_router(tracker.router)
