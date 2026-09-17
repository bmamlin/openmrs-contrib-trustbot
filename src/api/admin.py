"""Admin API endpoints: runtime log level control (and future admin UI).

Per openspec/specs/overview.md §5.5, application log level must be
changeable at runtime without restarting the service via a protected
admin endpoint. All admin endpoints require a valid ADMIN_API_TOKEN bearer
token when admin.require_auth is true (config.yaml) — see spec §6 for
security requirements. Endpoints here must never log secrets.

Not yet implemented — see NotImplementedError below.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/admin")


@router.post("/log-level")
async def set_log_level(level: str):
    """Change the running service's log level (DEBUG | INFO | WARNING | ERROR)."""
    raise NotImplementedError
