"""OpenMRS Trust Bot — FastAPI application entrypoint.

Wires together the API routers (health, webhooks, admin) into a single
FastAPI app. Run with:

    uvicorn src.main:app --host 0.0.0.0 --port 8080
"""

from fastapi import FastAPI

from src.api import admin, health, webhooks

app = FastAPI(title="OpenMRS Trust Bot")

app.include_router(health.router)
app.include_router(webhooks.router)
app.include_router(admin.router)
