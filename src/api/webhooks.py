"""POST /webhook/discourse — native Discourse webhooks and Discourse Workflows.

Per specs/discourse-webhook-trigger/spec.md and
specs/discourse-workflow-trigger/spec.md, this single endpoint handles two
distinct delivery mechanisms, branching on which header is present:

  Native Discourse webhook (X-Discourse-Event present):
    1. Verifies X-Discourse-Event-Signature (HMAC-SHA256 over the raw
       body, using DISCOURSE_WEBHOOK_SECRET); rejects with HTTP 403.
    2. Parses the JSON body.
    3. Looks up a parser for the X-Discourse-Event value (NOT
       X-Discourse-Event-Type, which is only the coarse delivery
       category — e.g. both user_badge_granted and user_badge_revoked
       share X-Discourse-Event-Type: user_badge; only X-Discourse-Event
       actually distinguishes them, confirmed via live capture). If no
       parser is registered for the name, acknowledges with HTTP 200
       and takes no action (not an error — see
       src/triggers/discourse_webhook.py). If a registered parser
       cannot resolve a target OpenMRS ID from the payload, rejects
       with HTTP 400 (a real error, not a silent no-op).
    4. Builds a `webhook` TriggerEvent and evaluates it against the
       rules engine.

  Discourse Workflow (X-Discourse-Workflow present, and no
  X-Discourse-Event):
    1. Verifies X-Discourse-Workflow-Secret (HMAC-SHA256 over the raw
       body, using DISCOURSE_WORKFLOW_SECRET); rejects with HTTP 403.
    2. Parses the JSON body; requires a top-level `username` field.
    3. Builds a `workflow` TriggerEvent (named after the header's
       value — any name, not a single hardcoded one) and evaluates it
       against the rules engine.

  Neither header present: HTTP 400.

Both branches respond HTTP 200 once processed, regardless of whether any
rule matched. There is no replay-window/staleness check (removed — every
action this service takes is idempotent, see
restructure-discourse-triggers design.md). There's no framework here
doing signature verification or request-context plumbing for us the way
slack-bolt does for the Slack commands — this module hand-rolls both.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import sqlite3
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Request

from src.engine import evaluator
from src.engine.loader import load_rules
from src.logging_setup import redact_headers
from src.ratelimit import RateLimiter
from src.triggers import discourse_webhook, discourse_workflow

logger = logging.getLogger(__name__)


@dataclass
class WebhookContext:
    """Per-router-instance context the webhook handler needs beyond the raw request."""

    webhook_secret: str
    workflow_secret: str
    discourse_base_url: str
    audit_conn: sqlite3.Connection
    rate_limiter: RateLimiter
    dry_run: bool = False


def _verify_signature(raw_body: bytes, signature_header: str | None, secret: str) -> bool:
    """Constant-time verification of a `sha256=<hex>` HMAC signature header."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    provided_digest = signature_header.removeprefix("sha256=")
    expected_digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided_digest, expected_digest)


def _parse_json_object(raw_body: bytes) -> dict:
    """Parse the request body as a JSON object. Raises ValueError on any problem."""
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")

    return payload


def _source_ip(request: Request) -> str:
    """Source IP for rate-limiting: first X-Forwarded-For address, else the connecting client."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def create_webhooks_router(
    *,
    webhook_secret: str,
    workflow_secret: str,
    discourse_base_url: str,
    audit_conn: sqlite3.Connection,
    rate_limiter: RateLimiter,
    dry_run: bool = False,
) -> APIRouter:
    """Construct and return the configured webhook router."""
    context = WebhookContext(
        webhook_secret=webhook_secret,
        workflow_secret=workflow_secret,
        discourse_base_url=discourse_base_url,
        audit_conn=audit_conn,
        rate_limiter=rate_limiter,
        dry_run=dry_run,
    )
    router = APIRouter()

    def _evaluate_and_execute(event) -> None:
        rule_set = load_rules()
        matched_rules = evaluator.evaluate(rule_set, event)
        for rule in matched_rules:
            evaluator.execute_rule(rule, event, conn=context.audit_conn, dry_run=context.dry_run)

    @router.post("/webhook/discourse")
    async def discourse_webhook_route(request: Request) -> dict:
        logger.debug("received request: headers=%s", redact_headers(dict(request.headers)))

        source_ip = _source_ip(request)
        if not context.rate_limiter.is_allowed(source_ip):
            logger.warning("Discourse webhook rate limit exceeded for source IP %s", source_ip)
            raise HTTPException(status_code=429, detail="rate limit exceeded")

        raw_body = await request.body()
        event_name = request.headers.get("X-Discourse-Event")
        workflow_name = request.headers.get("X-Discourse-Workflow")

        if event_name is not None:
            if not _verify_signature(
                raw_body, request.headers.get("X-Discourse-Event-Signature"), context.webhook_secret
            ):
                logger.warning("Discourse webhook rejected: invalid signature from %s", source_ip)
                raise HTTPException(status_code=403, detail="invalid signature")

            try:
                payload = _parse_json_object(raw_body)
                event = discourse_webhook.build_event(
                    event_name, payload, discourse_base_url=context.discourse_base_url
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            if event is None:
                return {"status": "ok"}

            _evaluate_and_execute(event)
            return {"status": "ok"}

        if workflow_name is not None:
            if not _verify_signature(
                raw_body, request.headers.get("X-Discourse-Workflow-Secret"), context.workflow_secret
            ):
                logger.warning("Discourse workflow rejected: invalid signature from %s", source_ip)
                raise HTTPException(status_code=403, detail="invalid signature")

            try:
                payload = _parse_json_object(raw_body)
                event = discourse_workflow.build_event(
                    workflow_name, payload, discourse_base_url=context.discourse_base_url
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            _evaluate_and_execute(event)
            return {"status": "ok"}

        raise HTTPException(status_code=400, detail="unrecognized request: no event-type or workflow header")

    return router
