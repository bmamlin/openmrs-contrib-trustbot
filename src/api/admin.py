"""Admin API endpoints: runtime log level control (and future admin UI).

Per openspec/specs/overview.md §5.5, application log level must be
changeable at runtime without restarting the service via a protected
admin endpoint. All admin endpoints require a valid ADMIN_API_TOKEN bearer
token when admin.require_auth is true (config.yaml) — see spec §6 for
security requirements. Endpoints here must never log secrets.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, HTTPException, Request

from src import logging_setup

logger = logging.getLogger(__name__)


def _is_authorized(request: Request, admin_api_token: str) -> bool:
    """Constant-time check of the Authorization: Bearer <token> header."""
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        return False
    provided_token = header.removeprefix("Bearer ")
    return hmac.compare_digest(provided_token, admin_api_token)


def create_admin_router(*, admin_api_token: str, require_auth: bool) -> APIRouter:
    """Construct and return the configured admin router."""
    router = APIRouter(prefix="/admin")

    @router.post("/log-level")
    async def set_log_level(request: Request, level: str) -> dict:
        """Change the running service's log level (DEBUG | INFO | WARNING | ERROR)."""
        logger.debug(
            "received request: headers=%s", logging_setup.redact_headers(dict(request.headers))
        )

        if require_auth and not _is_authorized(request, admin_api_token):
            logger.warning("Admin log-level change rejected: missing or invalid bearer token")
            raise HTTPException(status_code=401, detail="unauthorized")

        try:
            logging_setup.set_log_level(level)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        logger.debug("log level changed to %s", level.upper())
        return {"level": level.upper()}

    return router
