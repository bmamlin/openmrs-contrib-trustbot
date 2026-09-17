"""POST /webhook/discourse — Discourse webhook receiver.

Per openspec/specs/overview.md §5.2, this endpoint must, in order:
  1. Verify the Discourse webhook signature (DISCOURSE_WEBHOOK_SECRET)
     before any other processing; reject invalid/unsigned requests with 403.
  2. Reject payloads whose timestamp falls outside the configured replay
     window (discourse.webhook.replay_window_seconds, default 300s).
  3. Enforce rate limiting (rate_limiting.discourse_webhook in config.yaml),
     returning 429 on violation.
  4. Parse the event; ignore event types other than trust-level changes.
  5. On a valid trust level change event, hand off to
     src/engine/evaluator.py to evaluate all discourse_trust_level rules.

Not yet implemented — see NotImplementedError below.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.post("/webhook/discourse")
async def discourse_webhook(request: Request):
    raise NotImplementedError
