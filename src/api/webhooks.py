"""POST /webhook/discourse — Discourse Workflow webhook receiver.

Per specs/discourse-trust-level-trigger/spec.md and
openspec/changes/add-discourse-trust-level-trigger/design.md, this
endpoint, in order:
  1. Verifies the X-Discourse-Workflow-Secret HMAC-SHA256 signature
     (computed over the raw body) before any other processing; rejects
     invalid/missing signatures with HTTP 403.
  2. Checks X-Discourse-Workflow against the configured workflow name;
     rejects a mismatch with HTTP 400.
  3. Parses the JSON body (username, old_trust_level, new_trust_level,
     timestamp); rejects a malformed/incomplete payload with HTTP 400.
  4. Rejects a payload whose timestamp falls outside the configured
     replay window (past or future) with HTTP 400.
  5. Builds a discourse_trust_level TriggerEvent and evaluates it against
     the rules engine, exactly like the Slack command handlers do.
  6. Responds HTTP 200 once processed, regardless of whether any rule
     matched.

There's no framework here doing signature verification or request-context
plumbing for us the way slack-bolt does for the Slack commands — this
module hand-rolls both.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request

from src.engine import evaluator
from src.engine.loader import load_rules
from src.ratelimit import RateLimiter
from src.triggers.discourse import build_trust_level_event

REQUIRED_PAYLOAD_FIELDS = ("username", "old_trust_level", "new_trust_level", "timestamp")

logger = logging.getLogger(__name__)


@dataclass
class WebhookContext:
    """Per-router-instance context the webhook handler needs beyond the raw request."""

    webhook_secret: str
    replay_window_seconds: int
    workflow_name: str
    discourse_base_url: str
    audit_conn: sqlite3.Connection
    rate_limiter: RateLimiter


def _verify_signature(raw_body: bytes, signature_header: str | None, secret: str) -> bool:
    """Constant-time verification of the X-Discourse-Workflow-Secret header."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    provided_digest = signature_header.removeprefix("sha256=")
    expected_digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided_digest, expected_digest)


def _parse_payload(raw_body: bytes) -> dict:
    """Parse and validate the webhook JSON body. Raises ValueError on any problem."""
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")

    for field in REQUIRED_PAYLOAD_FIELDS:
        if field not in payload:
            raise ValueError(f"missing required field: {field}")

    if not isinstance(payload["username"], str) or not payload["username"]:
        raise ValueError("username must be a non-empty string")
    if not isinstance(payload["old_trust_level"], int) or isinstance(payload["old_trust_level"], bool):
        raise ValueError("old_trust_level must be an integer")
    if not isinstance(payload["new_trust_level"], int) or isinstance(payload["new_trust_level"], bool):
        raise ValueError("new_trust_level must be an integer")
    if not isinstance(payload["timestamp"], str):
        raise ValueError("timestamp must be a string")

    return payload


def _source_ip(request: Request) -> str:
    """Source IP for rate-limiting: first X-Forwarded-For address, else the connecting client."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_within_replay_window(timestamp: str, window_seconds: int) -> bool:
    """True if `timestamp` (ISO 8601) is within window_seconds of now, past or future."""
    try:
        event_time = datetime.fromisoformat(timestamp)
    except ValueError:
        return False
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=UTC)
    delta_seconds = abs((datetime.now(UTC) - event_time).total_seconds())
    return delta_seconds <= window_seconds


def create_webhooks_router(
    *,
    webhook_secret: str,
    replay_window_seconds: int,
    workflow_name: str,
    discourse_base_url: str,
    audit_conn: sqlite3.Connection,
    rate_limiter: RateLimiter,
) -> APIRouter:
    """Construct and return the configured webhook router."""
    context = WebhookContext(
        webhook_secret=webhook_secret,
        replay_window_seconds=replay_window_seconds,
        workflow_name=workflow_name,
        discourse_base_url=discourse_base_url,
        audit_conn=audit_conn,
        rate_limiter=rate_limiter,
    )
    router = APIRouter()

    @router.post("/webhook/discourse")
    async def discourse_webhook(request: Request) -> dict:
        source_ip = _source_ip(request)
        if not context.rate_limiter.is_allowed(source_ip):
            logger.warning("Discourse webhook rate limit exceeded for source IP %s", source_ip)
            raise HTTPException(status_code=429, detail="rate limit exceeded")

        raw_body = await request.body()

        if not _verify_signature(
            raw_body, request.headers.get("X-Discourse-Workflow-Secret"), context.webhook_secret
        ):
            logger.warning("Discourse webhook rejected: invalid signature from %s", source_ip)
            raise HTTPException(status_code=403, detail="invalid signature")

        if request.headers.get("X-Discourse-Workflow") != context.workflow_name:
            logger.warning(
                "Discourse webhook rejected: unrecognized workflow name %r from %s",
                request.headers.get("X-Discourse-Workflow"),
                source_ip,
            )
            raise HTTPException(status_code=400, detail="unrecognized workflow")

        try:
            payload = _parse_payload(raw_body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if not _is_within_replay_window(payload["timestamp"], context.replay_window_seconds):
            raise HTTPException(status_code=400, detail="timestamp outside replay window")

        event = build_trust_level_event(payload, discourse_base_url=context.discourse_base_url)
        rule_set = load_rules()
        matched_rules = evaluator.evaluate(rule_set, event)
        for rule in matched_rules:
            evaluator.execute_rule(rule, event, conn=context.audit_conn)

        return {"status": "ok"}

    return router
