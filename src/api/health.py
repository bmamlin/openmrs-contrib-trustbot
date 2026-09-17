"""GET /health — health check endpoint for Docker/monitoring integration.

Per spec (§6.6) this only needs to confirm the service process is up; it
does not need to verify connectivity to Keycloak/Discourse/Slack.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
